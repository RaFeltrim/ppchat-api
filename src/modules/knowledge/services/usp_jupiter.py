"""Integração com JupiterWeb (ICMC USP São Carlos): grades, ementas, equivalências e requerimento SUAP."""

import html as html_lib
import json
import re
import unicodedata
from datetime import datetime, timezone
from http.cookiejar import CookieJar
from pathlib import Path
from typing import Dict, List, Optional
from urllib.parse import urlencode, urljoin
from urllib.request import HTTPCookieProcessor, Request, build_opener, urlopen

import fitz

from src.modules.ingestion.models.curriculum import Curriculo, Disciplina, RequisitoGeral

USP_CURRICULA_FILE = "usp_curriculos.json"
USP_EMENTAS_FILE = "usp_ementas.json"
USP_STUDENT_FILE = "usp_aluno.json"
USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"

USP_COURSES = {
    "usp_bsi": {
        "key": "usp_bsi",
        "label": "USP · BSI (CAASO)",
        "curso": "Bacharelado em Sistemas de Informação (BSI)",
        "campus": "USP São Carlos (ICMC / CAASO)",
        "codcg": "55",
        "codcur": "55051",
        "codhab": "4",
        "duracao_semestres": 8,
    },
    "usp_bci": {
        "key": "usp_bci",
        "label": "USP · BCI / Comp. (CAASO)",
        "curso": "Bacharelado em Ciências de Computação (BCI/BCC)",
        "campus": "USP São Carlos (ICMC / CAASO)",
        "codcg": "55",
        "codcur": "55041",
        "codhab": "0",
        "duracao_semestres": 8,
    },
    "usp_est": {
        "key": "usp_est",
        "label": "USP · Estatística (CAASO)",
        "curso": "Bacharelado em Estatística e Ciência de Dados",
        "campus": "USP São Carlos (ICMC / CAASO)",
        "codcg": "55",
        "codcur": "55071",
        "codhab": "4",
        "duracao_semestres": 8,
    },
}

_STOPWORDS = {
    "para", "com", "dos", "das", "uma", "em", "de", "do", "da", "e", "a", "o",
    "introducao", "topicos", "fundamentos", "principios", "laboratorio", "pratica",
    "basica", "basico", "avancada", "avancado", "aplicada", "aplicado", "sistemas",
    "computacao", "software", "engenharia", "ciencia", "dados", "ii", "iii", "iv",
}


def _norm(text: str) -> str:
    nfd = unicodedata.normalize("NFD", text.lower())
    return "".join(ch for ch in nfd if unicodedata.category(ch) != "Mn")


def _clean_html(raw: str) -> str:
    txt = re.sub(r"<[^>]+>", " ", raw)
    txt = html_lib.unescape(txt)
    return re.sub(r"\s+", " ", txt).strip()


def _http_get(url: str, timeout: int = 18) -> str:
    req = Request(url, headers={"User-Agent": USER_AGENT})
    with urlopen(req, timeout=timeout) as resp:
        return resp.read().decode("iso-8859-1", errors="replace")


def parse_jupiter_grade(html_text: str, meta: dict) -> Curriculo:
    """Converte o HTML de `listarGradeCurricular` do JupiterWeb em um objeto `Curriculo`."""
    section_tipo = "obrigatoria"
    current_sem: Optional[int] = None
    seen: Dict[str, dict] = {}
    last_code: Optional[str] = None

    row_parts = re.split(r"(?=<tr\b)", html_text, flags=re.I)
    for chunk in row_parts:
        clean = _clean_html(chunk)
        if not clean:
            continue

        low = _norm(clean)
        if "disciplinas obrigatorias" in low:
            section_tipo = "obrigatoria"
        elif "disciplinas optativas eletivas" in low:
            section_tipo = "eletiva"
        elif "disciplinas optativas livres" in low:
            section_tipo = "optativa"

        m_sem = re.search(r"(\d+)\s*[º°o]\s*per[ií]odo\s*ideal", clean, re.I)
        if m_sem:
            current_sem = int(m_sem.group(1))

        m_disc = re.search(
            r'obterDisciplina\?sgldis=([A-Z0-9]+)[^>]*>\s*([A-Z0-9]+)\s*</a>\s*</td>\s*<td[^>]*>(.*?)</td>\s*'
            r'<td[^>]*>(.*?)</td>\s*<td[^>]*>(.*?)</td>\s*<td[^>]*>(.*?)</td>',
            chunk,
            re.S | re.I,
        )
        if m_disc:
            code = m_disc.group(1).strip().upper()
            name = _clean_html(m_disc.group(3)).upper()
            cred_aula = int(re.sub(r"\D", "", _clean_html(m_disc.group(4))) or 0)
            cred_trab = int(re.sub(r"\D", "", _clean_html(m_disc.group(5))) or 0)
            ch_total = float(re.sub(r"[^\d.]", "", _clean_html(m_disc.group(6))) or (cred_aula * 15))
            if code not in seen:
                seen[code] = {
                    "codigo": code,
                    "nome": name,
                    "semestre": current_sem if section_tipo == "obrigatoria" else (current_sem or None),
                    "tipo": section_tipo,
                    "aulas_semanais": cred_aula,
                    "total_aulas": cred_aula * 15,
                    "carga_horaria_ensino": ch_total,
                    "carga_horaria_extensao": 0.0,
                    "carga_horaria_total": ch_total,
                    "abordagem": "teorico_pratica" if cred_trab > 0 else "teorica",
                    "usa_laboratorio": cred_trab > 0 or "laboratorio" in _norm(name),
                    "pre_requisitos": [],
                    "grupos_conhecimento": [f"JupiterWeb ICMC ({meta['codcur']}/{meta['codhab']})"],
                    "topicos_principais": [],
                    "pagina_plano_ensino": None,
                }
            last_code = code
            continue

        if last_code and "txt_arial_8pt_red" in chunk and "requisito" in low:
            m_req = re.search(r"\b([A-Z]{2,4}\d{4}|\d{7})\b", clean)
            if m_req:
                req_code = m_req.group(1).upper()
                if req_code != last_code and req_code not in seen[last_code]["pre_requisitos"]:
                    seen[last_code]["pre_requisitos"].append(req_code)

    valid_codes = set(seen.keys())
    disciplinas: List[Disciplina] = []
    for item in seen.values():
        item["pre_requisitos"] = [r for r in item["pre_requisitos"] if r in valid_codes and r != item["codigo"]]
        disciplinas.append(Disciplina(**item))

    total_ch = sum(d.carga_horaria_total for d in disciplinas if d.tipo == "obrigatoria")
    return Curriculo(
        curso=meta["curso"],
        campus=meta["campus"],
        vigencia="JupiterWeb USP (consulta pública oficial)",
        duracao_semestres=meta["duracao_semestres"],
        carga_horaria_total_curso=total_ch,
        disciplinas=disciplinas,
        requisitos_gerais=[
            RequisitoGeral(
                item="Aluno Especial (USP São Carlos)",
                descricao="Matrícula em disciplinas isoladas via JupiterWeb/ICMC sujeita a edital semestral e vagas.",
                pagina=None,
            ),
            RequisitoGeral(
                item="Aproveitamento de Estudos no IFSP",
                descricao="Equivalência >= 75%/80% de carga horária e conteúdo programático mediante requerimento no SUAP.",
                pagina=48,
            ),
        ],
    )


def sync_usp_curricula(processed_dir: Path) -> Dict[str, dict]:
    """Baixa as grades curriculares de BSI, BCI/BCC e Estatística da USP São Carlos."""
    result: Dict[str, dict] = {}
    for key, meta in USP_COURSES.items():
        url = (
            "https://uspdigital.usp.br/jupiterweb/listarGradeCurricular"
            f"?codcg={meta['codcg']}&codcur={meta['codcur']}&codhab={meta['codhab']}&tipo=N"
        )
        html_text = _http_get(url)
        curriculo = parse_jupiter_grade(html_text, meta)
        result[key] = curriculo.model_dump()

    processed_dir.mkdir(parents=True, exist_ok=True)
    (processed_dir / USP_CURRICULA_FILE).write_text(
        json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return result


def load_usp_aluno(processed_dir: Path) -> Optional[dict]:
    path = processed_dir / USP_STUDENT_FILE
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else None
    except Exception:
        return None


def load_usp_curricula(processed_dir: Path) -> Dict[str, Curriculo]:
    path = processed_dir / USP_CURRICULA_FILE
    if not path.exists():
        return {}
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
        curricula = {k: Curriculo.model_validate(v) for k, v in raw.items()}
    except Exception:
        return {}

    # Garante que disciplinas cursadas/em andamento pelo aluno especial apareçam no Fluxograma e Grade
    aluno = load_usp_aluno(processed_dir)
    extra_discs = (aluno or {}).get("disciplinas_aluno") or []
    if extra_discs:
        for cur in curricula.values():
            existing = {d.codigo for d in cur.disciplinas}
            added = []
            for item in extra_discs:
                code = (item.get("codigo") or "").upper()
                if code and code not in existing:
                    try:
                        disc_obj = Disciplina.model_validate(item)
                        cur.disciplinas.append(disc_obj)
                        added.append(disc_obj)
                        existing.add(code)
                    except Exception:
                        pass
            for disc_obj in added:
                disc_obj.pre_requisitos = [p for p in disc_obj.pre_requisitos if p in existing and p != disc_obj.codigo]
    return curricula


def fetch_usp_ementa(sgldis: str, processed_dir: Optional[Path] = None) -> dict:
    """Busca (com cache em disco) a ementa oficial de uma disciplina no JupiterWeb."""
    code = sgldis.strip().upper()
    cache_path = (processed_dir / USP_EMENTAS_FILE) if processed_dir else None
    cache: Dict[str, dict] = {}
    if cache_path and cache_path.exists():
        try:
            cache = json.loads(cache_path.read_text(encoding="utf-8"))
        except Exception:
            cache = {}
    if code in cache:
        return cache[code]

    url = f"https://uspdigital.usp.br/jupiterweb/obterDisciplina?sgldis={code}"
    html_text = _http_get(url)
    # Remove scripts/styles before extracting visible sections
    no_script = re.sub(r"<(script|style)[^>]*>.*?</\1>", " ", html_text, flags=re.S | re.I)
    lines = [_clean_html(line) for line in re.split(r"</?(?:tr|p|br|div|td|th|li|b)[^>]*>", no_script, flags=re.I)]
    lines = [ln for ln in lines if ln and ln != "\xa0"]

    def _section(headers: tuple, stop_headers: tuple) -> str:
        norm_targets = {_norm(h) for h in headers}
        for i, ln in enumerate(lines):
            if _norm(ln) in norm_targets:
                buf = []
                for nxt in lines[i + 1 :]:
                    if any(_norm(nxt).startswith(_norm(s)) for s in stop_headers):
                        break
                    buf.append(nxt)
                return " ".join(buf).strip()
        return ""

    stops = ("Conteúdo Programático", "Programa Resumido", "Programa", "Instrumentos e Critérios", "Método de Avaliação", "Avaliação", "Bibliografia", "Atividades de Extensão")
    title = next((ln for ln in lines if ln.startswith(f"Disciplina: {code}")), code)
    ch_match = re.search(r"Carga Hor[áa]ria Total:\s*(\d+\s*h)", " ".join(lines), re.I)
    info = {
        "codigo": code,
        "titulo": title.replace("Disciplina:", "").strip(),
        "carga_horaria": ch_match.group(1) if ch_match else "",
        "objetivos": _section(("Objetivos",), stops),
        "programa_resumido": _section(("Programa Resumido", "Conteúdo Programático"), ("Programa", "Instrumentos e Critérios", "Método de Avaliação", "Avaliação", "Bibliografia")),
        "programa": _section(("Conteúdo Programático", "Programa"), ("Instrumentos e Critérios", "Método de Avaliação", "Avaliação", "Bibliografia", "Atividades de Extensão"))[:3000],
        "bibliografia": _section(("Bibliografia", "Bibliografia Principal"), ("Bibliografia Complementar", "Docente", "Créditos", "Atividades de Extensão"))[:1200],
        "url": url,
    }
    if cache_path:
        cache[code] = info
        cache_path.parent.mkdir(parents=True, exist_ok=True)
        cache_path.write_text(json.dumps(cache, ensure_ascii=False, indent=2), encoding="utf-8")
    return info


def check_jupiter_auth(usp_user: str, usp_password: str) -> dict:
    """Valida autenticação no JupiterWeb (codpes/senusu) para consulta autenticada (menu 8382)."""
    if not usp_user or not usp_password:
        return {"authenticated": False, "reason": "USP_USER ou USP_PASSWORD não configurados no .env."}
    jar = CookieJar()
    opener = build_opener(HTTPCookieProcessor(jar))
    opener.addheaders = [("User-Agent", USER_AGENT)]
    body = urlencode({"codpes": usp_user, "senusu": usp_password, "Submit": "Entrar"}).encode("utf-8")
    try:
        with opener.open("https://uspdigital.usp.br/jupiterweb/autenticar", data=body, timeout=15) as resp:
            html_out = resp.read().decode("iso-8859-1", errors="replace")
        with opener.open("https://uspdigital.usp.br/jupiterweb/webMenuNavegacao.jsp?codmnu=8382", timeout=15) as r2:
            _ = r2.read().decode("iso-8859-1", errors="replace")
        ok = "webLogin.jsp" not in resp.geturl() and "usuário ou senha" not in _norm(html_out)
        return {"authenticated": ok, "menu_status": r2.status, "has_session_cookie": len(jar) > 0, "sso_url": "https://idpcafe.usp.br/idp/profile/SAML2/Redirect/SSO?execution=e1s1"}
    except Exception as exc:
        return {"authenticated": False, "reason": str(exc)}


def _jupiter_dwr(opener, jsession: str, script_name: str, method_name: str, params: List[str], page: str = "/jupiterweb/gradeHoraria?codmnu=8385") -> str:
    body = "\n".join([
        "callCount=1",
        "windowName=",
        f"c0-scriptName={script_name}",
        f"c0-methodName={method_name}",
        "c0-id=0",
        *params,
        "batchId=1",
        "instanceId=0",
        f"page={page}",
        f"httpSessionId={jsession}",
        "scriptSessionId=12345678901234567890123456789012",
        "",
    ]).encode("utf-8")
    req = Request(
        f"https://uspdigital.usp.br/jupiterweb/dwr/call/plaincall/{script_name}.{method_name}.dwr",
        data=body,
        headers={"User-Agent": USER_AGENT, "Content-Type": "text/plain"},
    )
    with opener.open(req, timeout=20) as resp:
        return resp.read().decode("utf-8", errors="replace")


def _parse_he_pdf_disciplines(pdf_bytes: bytes) -> List[dict]:
    """Extrai disciplinas, notas, frequências e semestres do PDF oficial do Histórico Escolar JupiterWeb."""
    if b"%PDF" not in pdf_bytes[:32]:
        return []
    with fitz.open(stream=pdf_bytes, filetype="pdf") as doc:
        full_text = "\n".join(page.get_text("text") for page in doc)

    lines = [ln.strip() for ln in full_text.splitlines() if ln.strip()]
    cur_period = ""
    records: List[dict] = []
    i = 0
    while i < len(lines):
        ln = lines[i]
        m_per = re.match(r"(\d{4})\s+([12])[º°o]?\.\s*Semestre", ln, re.I)
        if m_per:
            cur_period = f"{m_per.group(1)}/{m_per.group(2)}"
            i += 1
            continue

        if re.match(r"^(?:[A-Z]{2,4}\d{4}|\d{7})$", ln) and i + 1 < len(lines):
            code = ln.upper()
            nome = lines[i + 1]
            j = i + 2
            nums: List[str] = []
            nota = None
            concept = None
            while j < len(lines):
                nxt = lines[j]
                if nxt.startswith("Créditos acumulados") or nxt.startswith("____") or nxt.startswith("Certificado"):
                    break
                if re.match(r"^(?:[A-Z]{2,4}\d{4}|\d{7})$", nxt):
                    break
                m_res = re.match(r"^(\d+(?:[.,]\d+)?)\s+(A|RN|RA|RF|T|MA)$", nxt)
                if m_res:
                    nota = m_res.group(1).replace(".", ",")
                    concept = m_res.group(2)
                    j += 1
                    break
                if re.match(r"^(?:MA|T|A|RN|RA|RF)$", nxt):
                    concept = nxt
                    j += 1
                    break
                if re.match(r"^\d+$", nxt):
                    nums.append(nxt)
                j += 1

            au = int(nums[0]) if len(nums) >= 1 else 2
            tr = int(nums[1]) if len(nums) >= 2 else 0
            ch = float(nums[2]) if len(nums) >= 3 else float(au * 15 + tr * 30)
            freq = f"{nums[-1]}%" if len(nums) >= 4 else None
            st = "concluida" if concept == "A" else "reprovada" if concept in {"RN", "RA", "RF"} else "cursando"
            sit_map = {
                "A": "Aprovado (Aluno Especial)",
                "MA": "Matriculado (Aluno Especial)",
                "RN": "Reprovado por Nota",
                "RA": "Reprovado por Nota e Frequência",
                "RF": "Reprovado por Frequência",
                "T": "Trancado",
            }
            records.append({
                "codigo": code,
                "nome": nome,
                "au": au,
                "tr": tr,
                "ch": ch,
                "freq": freq,
                "nota": nota,
                "situacao": sit_map.get(concept or "", concept or "Cursada"),
                "status": st,
                "periodo": cur_period or "2026/1",
            })
            i = j
            continue
        i += 1
    return records


def _fetch_jupiter_student(usp_user: str, usp_password: str, processed_dir: Optional[Path] = None) -> dict:
    """Coleta histórico (disciplinas já realizadas) e grade horária atual no JupiterWeb."""
    jar = CookieJar()
    opener = build_opener(HTTPCookieProcessor(jar))
    headers = {"User-Agent": USER_AGENT}

    opener.open(Request("https://uspdigital.usp.br/jupiterweb/webLogin.jsp", headers=headers), timeout=20)
    login_data = urlencode({"codpes": usp_user, "senusu": usp_password, "Submit": "Entrar", "url": ""}).encode("iso-8859-1")
    with opener.open(
        Request(
            "https://uspdigital.usp.br/jupiterweb/autenticar",
            data=login_data,
            headers={**headers, "Content-Type": "application/x-www-form-urlencoded", "Referer": "https://uspdigital.usp.br/jupiterweb/webLogin.jsp"},
        ),
        timeout=20,
    ) as resp:
        login_html = resp.read().decode("iso-8859-1", errors="replace")

    if "usuário ou senha" in _norm(login_html) and "sair" not in _norm(login_html):
        raise RuntimeError("Falha de login no JupiterWeb (verifique USP_USER/USP_PASSWORD).")

    jsession = next((c.value for c in jar if c.name == "JSESSIONID"), "")

    # 1. Programa & Nome do aluno
    prog_raw = _jupiter_dwr(opener, jsession, "EmissaoHEControleDWR", "obterProgramaEmissaoHE", [f"c0-param0=string:{usp_user}"], "/jupiterweb/historicoEscolar?codmnu=8383")
    m_nom = re.search(r'nompes:"([^"]+)"', prog_raw)
    m_clg = re.search(r'codpgmclg:"([^"]+)"', prog_raw)
    m_pgm = re.search(r'codpgm:(\d+)', prog_raw)
    raw_nom = m_nom.group(1) if m_nom else "Aluno USP"
    nome_aluno = re.sub(r"\\u([0-9a-fA-F]{4})", lambda m: chr(int(m.group(1), 16)), raw_nom).strip()
    codpgmclg = (m_clg.group(1) if m_clg else "1/E/55").replace(r"\/", "/")
    codpgm = m_pgm.group(1) if m_pgm else "1"

    # 2. Grade Horária atual (disciplinas cursando no semestre vigente)
    gh_raw = _jupiter_dwr(opener, jsession, "GradeHorariaControleDWR", "obterGradeHoraria", [f"c0-param0=string:{usp_user}", f"c0-param1=string:{codpgm}"])
    enrolled: Dict[str, dict] = {}
    day_names = {"seg": "Seg", "ter": "Ter", "qua": "Qua", "qui": "Qui", "sex": "Sex", "sab": "Sáb", "dom": "Dom"}
    # Extrai cada bloco de horário do callback DWR
    for obj_m in re.finditer(r"\{[^{}]*\}", gh_raw):
        blk = obj_m.group(0)
        h_ini = re.search(r'horent:"([^"]+)"', blk)
        h_fim = re.search(r'horsai:"([^"]+)"', blk)
        slot_time = f"{h_ini.group(1)}–{h_fim.group(1)}" if (h_ini and h_fim) else ""
        for dkey, dlabel in day_names.items():
            m_cell = re.search(rf'{dkey}:"([^"]*)"', blk)
            if not m_cell:
                continue
            for m_sub in re.finditer(r"\$([A-Z0-9]{7})-(\d+)-([A-Z])", m_cell.group(1)):
                code, turma, sit = m_sub.group(1).upper(), m_sub.group(2), m_sub.group(3)
                sem_guess = f"{turma[:4]}/{1 if turma[4:5] == '1' else 2}" if len(turma) >= 5 else "2026/2"
                sched = f"{dlabel} {slot_time}".strip()
                entry = enrolled.setdefault(code, {
                    "codigo": code,
                    "turma": turma,
                    "periodo": sem_guess,
                    "status": "cursando" if sit in {"M", "I", "P"} else "concluida",
                    "horarios": [],
                })
                if sched and sched not in entry["horarios"]:
                    entry["horarios"].append(sched)

    # 3. Histórico Escolar Final PDF (disciplinas realizadas)
    _jupiter_dwr(opener, jsession, "EmissaoHEControleDWR", "verificarEmissaoHE_Especial", [f"c0-param0=string:{usp_user}", f"c0-param1=string:{codpgmclg}"], "/jupiterweb/historicoEscolar?codmnu=8383")
    he_query = urlencode({
        "cmd": "cmd",
        "codmnu": "8383",
        "codpes": usp_user,
        "nompes": nome_aluno,
        "codpgmclg": codpgmclg,
        "codcurhab": "0/0/Especial",
        "previewhefinal": "S",
    })
    with opener.open(Request(f"https://uspdigital.usp.br/jupiterweb/historicoescolarListar?{he_query}", headers=headers), timeout=25) as r_he:
        he_bytes = r_he.read()
    he_records = _parse_he_pdf_disciplines(he_bytes)

    return {
        "nome": nome_aluno,
        "codpgmclg": codpgmclg,
        "enrolled": enrolled,
        "he_records": he_records,
    }


def _fetch_edisciplinas_student(usp_user: str, usp_password: str) -> List[dict]:
    """Autentica no e-Disciplinas USP via idpcafe.usp.br e lista cursos, tarefas e materiais."""
    jar = CookieJar()
    opener = build_opener(HTTPCookieProcessor(jar))
    headers = {"User-Agent": USER_AGENT}

    with opener.open(Request("https://edisciplinas.usp.br/auth/shibboleth/index.php", headers=headers), timeout=20) as r_ed:
        ed_url = r_ed.geturl()
        ed_html = r_ed.read().decode("utf-8", errors="replace")

    m_form = re.search(r'<form[^>]+action=["\']([^"\']+)["\'][^>]*>(.*?)</form>', ed_html, re.S | re.I)
    if not m_form:
        return []
    idp_action = urljoin(ed_url, html_lib.unescape(m_form.group(1)))
    idp_post = urlencode({"j_username": usp_user, "j_password": usp_password, "_eventId_proceed": ""}).encode("utf-8")
    with opener.open(
        Request(idp_action, data=idp_post, headers={**headers, "Content-Type": "application/x-www-form-urlencoded", "Referer": ed_url}),
        timeout=20,
    ) as r_idp:
        idp_html = r_idp.read().decode("utf-8", errors="replace")

    m_saml = re.search(r'<form[^>]+action=["\']([^"\']+)["\'][^>]*>(.*?)</form>', idp_html, re.S | re.I)
    if not m_saml:
        return []
    saml_action = html_lib.unescape(m_saml.group(1))
    saml_fields = {
        m_in.group(1): html_lib.unescape(m_in.group(2))
        for m_in in re.finditer(r'<input[^>]+name=["\']([^"\']+)["\'][^>]+value=["\']([^"\']*)["\']', m_saml.group(2), re.S | re.I)
    }
    if "SAMLResponse" not in saml_fields:
        return []

    with opener.open(
        Request(saml_action, data=urlencode(saml_fields).encode("utf-8"), headers={**headers, "Content-Type": "application/x-www-form-urlencoded"}),
        timeout=25,
    ) as r_sp:
        sp_html = r_sp.read().decode("utf-8", errors="replace")

    m_sk = re.search(r'"sesskey"\s*:\s*"([^"]+)"', sp_html)
    if not m_sk:
        return []
    sk = m_sk.group(1)

    ajax_url = f"https://edisciplinas.usp.br/lib/ajax/service.php?sesskey={sk}"
    payload = json.dumps([
        {
            "index": 0,
            "methodname": "core_course_get_enrolled_courses_by_timeline_classification",
            "args": {"offset": 0, "limit": 50, "classification": "all", "sort": "fullname"},
        }
    ]).encode("utf-8")
    with opener.open(Request(ajax_url, data=payload, headers={**headers, "Content-Type": "application/json"}), timeout=20) as r_ajax:
        raw_courses = json.loads(r_ajax.read().decode("utf-8", errors="replace"))[0].get("data", {}).get("courses", [])

    courses_out: List[dict] = []
    for c in raw_courses:
        cid = c.get("id")
        fullname = c.get("fullname") or ""
        shortname = c.get("shortname") or ""
        m_code = re.search(r"\b([A-Z]{2,4}\d{4})\b", f"{shortname} {fullname}", re.I)
        code = m_code.group(1).upper() if m_code else shortname.upper()
        viewurl = c.get("viewurl") or f"https://edisciplinas.usp.br/course/view.php?id={cid}"

        tasks: List[dict] = []
        materials: List[dict] = []
        seen_urls = set()
        try:
            with opener.open(Request(viewurl, headers=headers), timeout=20) as r_c:
                c_html = r_c.read().decode("utf-8", errors="replace")
            for m_mod in re.finditer(
                r'<a[^>]+href=["\'](https://edisciplinas\.usp\.br/mod/(assign|quiz|resource|url)/view\.php\?id=\d+)["\'][^>]*>(.*?)</a>',
                c_html,
                re.S | re.I,
            ):
                m_url, m_type, m_raw = m_mod.group(1), m_mod.group(2).lower(), m_mod.group(3)
                if m_url in seen_urls:
                    continue
                seen_urls.add(m_url)
                title = _clean_html(re.sub(r"\s+(?:Tarefa|Arquivo|URL)\s*$", "", _clean_html(m_raw)))
                if not title:
                    continue
                item = {"title": title, "url": m_url, "mod_type": m_type}
                if m_type in {"assign", "quiz"}:
                    tasks.append(item)
                else:
                    materials.append(item)
        except Exception:
            pass

        courses_out.append({
            "id": cid,
            "code": code,
            "shortname": shortname,
            "fullname": fullname,
            "summary": _clean_html(c.get("summary") or ""),
            "viewurl": viewurl,
            "tasks": tasks,
            "materials": materials,
        })
    return courses_out


def sync_usp_student_data(usp_user: str, usp_password: str, processed_dir: Path, force: bool = False) -> dict:
    """Sincroniza disciplinas realizadas e em curso (JupiterWeb + e-Disciplinas USP)."""
    cache_path = processed_dir / USP_STUDENT_FILE
    if not force and cache_path.exists():
        cached = load_usp_aluno(processed_dir)
        if cached and cached.get("status"):
            return cached

    if not usp_user or not usp_password:
        return load_usp_aluno(processed_dir) or {
            "inst": "usp",
            "nome": "Aluno USP",
            "matricula": "Aluno Especial · ICMC/USP",
            "coletado_em": None,
            "status": {},
            "notas": {},
            "disciplinas_aluno": [],
            "edisciplinas_courses": [],
            "contexto": "",
            "error": "USP_USER ou USP_PASSWORD não configurados no .env.",
        }

    jup = _fetch_jupiter_student(usp_user, usp_password, processed_dir=processed_dir)
    ed_courses = _fetch_edisciplinas_student(usp_user, usp_password)
    ed_by_code = {c["code"]: c for c in ed_courses}

    status_map: Dict[str, str] = {}
    notas_map: Dict[str, dict] = {}
    disciplinas_aluno: Dict[str, dict] = {}

    # Base curricula lookup for enrichment
    existing_cur = load_usp_curricula(processed_dir)
    known_discs: Dict[str, Disciplina] = {}
    for cur in existing_cur.values():
        for d in cur.disciplinas:
            known_discs.setdefault(d.codigo, d)

    # 1. Histórico Escolar (concluídas/reprovadas)
    for rec in jup.get("he_records", []):
        code = rec["codigo"]
        status_map[code] = rec["status"]
        notas_map[code] = {
            "nota": rec["nota"],
            "freq": rec["freq"] or "-",
            "periodo": rec["periodo"],
            "situacao": rec["situacao"],
            "ch": rec["ch"],
        }
        base = known_discs.get(code)
        disciplinas_aluno[code] = {
            "codigo": code,
            "nome": (base.nome if base else rec["nome"]).upper(),
            "semestre": base.semestre if base else 5,
            "tipo": base.tipo if base else "eletiva",
            "aulas_semanais": base.aulas_semanais if base else rec["au"],
            "total_aulas": base.total_aulas if base else rec["au"] * 15,
            "carga_horaria_ensino": base.carga_horaria_ensino if base else rec["ch"],
            "carga_horaria_extensao": 0.0,
            "carga_horaria_total": base.carga_horaria_total if base else rec["ch"],
            "abordagem": base.abordagem if base else "teorico_pratica",
            "usa_laboratorio": base.usa_laboratorio if base else True,
            "pre_requisitos": base.pre_requisitos if base else [],
            "grupos_conhecimento": [f"JupiterWeb ICMC (Realizada {rec['periodo']})"],
            "topicos_principais": (base.topicos_principais if base and base.topicos_principais else []),
            "pagina_plano_ensino": None,
        }

    # 2. Grade Horária atual (cursando agora)
    for code, en in jup.get("enrolled", {}).items():
        status_map[code] = en["status"]
        base = known_discs.get(code)
        ed = ed_by_code.get(code)
        ementa = {}
        if not base:
            try:
                ementa = fetch_usp_ementa(code, processed_dir)
            except Exception:
                ementa = {}
        name = (base.nome if base else (ed["fullname"].split("-", 1)[-1].split("(")[0].strip() if ed else code)).upper()
        ch = base.carga_horaria_total if base else 90.0
        sched = ", ".join(en.get("horarios", []))
        notas_map[code] = {
            "nota": None,
            "freq": "Em curso",
            "periodo": en["periodo"],
            "situacao": f"Matriculado{f' · {sched}' if sched else ''} (Turma {en['turma']})",
            "ch": ch,
        }
        disciplinas_aluno[code] = {
            "codigo": code,
            "nome": name,
            "semestre": base.semestre if base else 4,
            "tipo": base.tipo if base else "obrigatoria",
            "aulas_semanais": base.aulas_semanais if base else 4,
            "total_aulas": base.total_aulas if base else 60,
            "carga_horaria_ensino": ch,
            "carga_horaria_extensao": 0.0,
            "carga_horaria_total": ch,
            "abordagem": base.abordagem if base else "teorico_pratica",
            "usa_laboratorio": True,
            "pre_requisitos": base.pre_requisitos if base else [],
            "grupos_conhecimento": [f"JupiterWeb ICMC (Cursando {en['periodo']})"],
            "topicos_principais": (base.topicos_principais if base and base.topicos_principais else []),
            "pagina_plano_ensino": None,
        }

    # Enriquece cada disciplina do aluno com tópico/ementa do JupiterWeb se vazio
    for code, disc_dict in disciplinas_aluno.items():
        if not disc_dict["topicos_principais"]:
            try:
                em = fetch_usp_ementa(code, processed_dir)
                prog = em.get("programa") or em.get("programa_resumido") or em.get("objetivos") or ""
                if prog:
                    parts = [p.strip(" .;-") for p in re.split(r"(?:\d+\.|\n|;)", prog) if len(p.strip()) > 6]
                    disc_dict["topicos_principais"] = parts[:8]
            except Exception:
                pass

    # Enriquece lista de cursos do e-Disciplinas com status/nota do JupiterWeb
    for c in ed_courses:
        code = c["code"]
        meta_n = notas_map.get(code, {})
        c["status"] = status_map.get(code, "cursando")
        c["nota"] = meta_n.get("nota")
        c["freq"] = meta_n.get("freq")
        c["periodo"] = meta_n.get("periodo") or "2026"
        c["situacao"] = meta_n.get("situacao") or "Matriculado no e-Disciplinas"
        c["ch"] = meta_n.get("ch") or disciplinas_aluno.get(code, {}).get("carga_horaria_total")

    lines = [
        f"Aluno USP São Carlos (ICMC - Aluno Especial): {jup.get('nome', 'Rafael Feltrim')}",
        "Vínculo JupiterWeb: Aluno Especial (ICMC · CAASO)",
    ]
    for code, st in status_map.items():
        n = notas_map.get(code, {})
        dname = disciplinas_aluno.get(code, {}).get("nome", code)
        lines.append(
            f"- {code} ({dname}): status={st}, período={n.get('periodo')}, CH={n.get('ch')}h, freq={n.get('freq')}, nota={n.get('nota') or '-'} ({n.get('situacao')})"
        )
    if ed_courses:
        lines.append("Disciplinas no e-Disciplinas USP (Moodle):")
        for c in ed_courses:
            lines.append(f"- {c['code']} ({c['fullname']}) — {c.get('viewurl', '')}")
            if c.get("summary"):
                lines.append(f"  Resumo: {c['summary'][:300]}")
            if c.get("tasks"):
                lines.append("  Tarefas: " + "; ".join(t["title"] for t in c["tasks"][:15]))
            if c.get("materials"):
                lines.append("  Materiais: " + "; ".join(m["title"] for m in c["materials"][:15]))

    result = {
        "inst": "usp",
        "nome": jup.get("nome") or "Rafael Feltrim",
        "matricula": f"Aluno Especial · ICMC/USP ({jup.get('codpgmclg', '1/E/55')})",
        "coletado_em": datetime.now(timezone.utc).isoformat(),
        "status": status_map,
        "notas": notas_map,
        "disciplinas_aluno": list(disciplinas_aluno.values()),
        "edisciplinas_courses": ed_courses,
        "contexto": "\n".join(lines),
    }

    processed_dir.mkdir(parents=True, exist_ok=True)
    cache_path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    return result


def _sig_tokens(name: str) -> set:
    words = re.findall(r"[a-z0-9]{3,}", _norm(name))
    return {w for w in words if w not in _STOPWORDS}


def _level_num(name: str) -> Optional[str]:
    m = re.search(r"\b(iii|ii|iv|i|1|2|3|4)\b", _norm(name))
    if not m:
        return None
    return {"i": "1", "ii": "2", "iii": "3", "iv": "4"}.get(m.group(1), m.group(1))


def compute_equivalences(ifsp: Curriculo, usp_map: Dict[str, Curriculo], curso_filter: str = "all") -> List[dict]:
    """Calcula equivalências candidatas entre USP São Carlos (BSI/BCI/Estatística) e IFSP BES."""
    matches: List[dict] = []
    skip_ifsp = {"SCLING1", "SCLING2", "SCLCLIBR", "SCLAXB1", "SCLAXB2", "SCLAXB3", "SCLAXB4"}

    for usp_key, usp_cur in usp_map.items():
        if curso_filter != "all" and usp_key != curso_filter:
            continue
        course_label = USP_COURSES.get(usp_key, {}).get("label", usp_key)
        for u in usp_cur.disciplinas:
            u_toks = _sig_tokens(u.nome)
            if not u_toks:
                continue
            u_lvl = _level_num(u.nome)
            for f in ifsp.disciplinas:
                if f.codigo in skip_ifsp:
                    continue
                f_toks = _sig_tokens(f.nome)
                if not f_toks:
                    continue
                inter = u_toks & f_toks
                if not inter:
                    continue
                union = u_toks | f_toks
                jaccard = len(inter) / len(union)
                coverage_ifsp = len(inter) / len(f_toks)
                score = 0.55 * jaccard + 0.45 * coverage_ifsp

                f_lvl = _level_num(f.nome)
                if u_lvl and f_lvl and u_lvl != f_lvl:
                    score -= 0.15

                ch_ratio = (u.carga_horaria_total / f.carga_horaria_total) if f.carga_horaria_total else 1.0
                if score < 0.35:
                    continue

                pct = min(99, round(score * 100))
                if pct >= 70 and ch_ratio >= 0.75:
                    nivel = "Alta"
                elif pct >= 45 and ch_ratio >= 0.5:
                    nivel = "Parcial"
                else:
                    continue

                matches.append({
                    "usp_curso": usp_key,
                    "usp_curso_label": course_label,
                    "usp_codigo": u.codigo,
                    "usp_nome": u.nome,
                    "usp_ch": u.carga_horaria_total,
                    "ifsp_codigo": f.codigo,
                    "ifsp_nome": f.nome,
                    "ifsp_ch": f.carga_horaria_total,
                    "ifsp_semestre": f.semestre,
                    "ch_ratio": round(ch_ratio, 2),
                    "similaridade_pct": pct,
                    "equivalencia": nivel,
                    "termos_comuns": sorted(inter),
                })

    matches.sort(key=lambda m: (0 if m["equivalencia"] == "Alta" else 1, -m["similaridade_pct"], -m["ch_ratio"]))
    return matches


def build_suap_requerimento(
    ifsp_disc: Disciplina,
    usp_disc: Disciplina,
    usp_ementa: dict,
    usp_curso_label: str,
    aluno_nome: str = "",
    matricula: str = "",
) -> dict:
    """Gera a minuta formal do Requerimento de Aproveitamento de Estudos para envio via SUAP."""
    ch_ifsp = ifsp_disc.carga_horaria_total or 0
    ch_usp = usp_disc.carga_horaria_total or 0
    ratio_pct = round((ch_usp / ch_ifsp) * 100) if ch_ifsp else 100
    atende_ch = ratio_pct >= 75

    topicos_ifsp = "\n".join(f"- {t}" for t in ifsp_disc.topicos_principais) or "- (Consultar plano de ensino no PPC)"
    programa_usp = usp_ementa.get("programa_resumido") or usp_ementa.get("programa") or usp_ementa.get("objetivos") or "Consultar ementa no JupiterWeb."

    minuta = f"""# REQUERIMENTO DE APROVEITAMENTO DE ESTUDOS — SUAP / IFSP SÃO CARLOS

**Solicitante:** {aluno_nome or "[Nome Completo do(a) Estudante]"}
**Prontuário / Matrícula SUAP:** {matricula or "[SCXXXXXXX]"}
**Curso de Destino:** Bacharelado em Engenharia de Software (BES) — IFSP Câmpus São Carlos
**Instituição de Origem (Aluno Especial):** {usp_curso_label}

---

## 1. Disciplinas Comparadas
| Campo | Disciplina Cursada na USP | Disciplina Pretendida no IFSP |
|---|---|---|
| **Código** | `{usp_disc.codigo}` | `{ifsp_disc.codigo}` |
| **Nome** | {usp_disc.nome} | {ifsp_disc.nome} |
| **Carga Horária** | {ch_usp:.0f} h | {ch_ifsp:.1f} h |
| **Referência Oficial** | [JupiterWeb ({usp_disc.codigo})]({usp_ementa.get('url', '')}) | PPC BES [Página {ifsp_disc.pagina_plano_ensino or 48}] |

**Análise de Carga Horária:** {ch_usp:.0f} h / {ch_ifsp:.1f} h = **{ratio_pct}%** ({"atende ao mínimo de 75% de carga horária" if atende_ch else "atenção: carga horária abaixo de 75% — verificar complementação"}).

---

## 2. Comparativo de Conteúdo Programático

### Ementa Oficial USP (`{usp_disc.codigo}`)
{programa_usp[:1500]}

### Conteúdo Programático IFSP (`{ifsp_disc.codigo}`)
{topicos_ifsp}

---

## 3. Documentos Obrigatórios para Anexar no SUAP
1. Histórico Escolar / Atestado de Aprovação como **Aluno Especial** emitido pela USP (JupiterWeb).
2. Programa / Ementa oficial autenticada de `{usp_disc.codigo}` ({usp_ementa.get('url', '')}).
3. Planilha/Formulário oficial de Aproveitamento de Estudos (DDGA/CRA): `aproveitamento_estudos.xls` (disponível no Drive IFSP / Módulo de Requerimentos do SUAP).

**Fundamentação:** Artigos de Aproveitamento de Estudos do PPC BES (IFSP São Carlos, [Página 48], exigindo equivalência mínima de conteúdo e carga horária).
"""
    return {
        "ifsp_codigo": ifsp_disc.codigo,
        "usp_codigo": usp_disc.codigo,
        "ch_ratio_pct": ratio_pct,
        "atende_ch_75": atende_ch,
        "minuta_markdown": minuta,
    }
