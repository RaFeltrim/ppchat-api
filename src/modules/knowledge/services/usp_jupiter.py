"""Integração com JupiterWeb (ICMC USP São Carlos): grades, ementas, equivalências e requerimento SUAP."""

import html as html_lib
import json
import re
import unicodedata
from http.cookiejar import CookieJar
from pathlib import Path
from typing import Dict, List, Optional
from urllib.parse import urlencode
from urllib.request import HTTPCookieProcessor, Request, build_opener, urlopen

from src.modules.ingestion.models.curriculum import Curriculo, Disciplina, RequisitoGeral

USP_CURRICULA_FILE = "usp_curriculos.json"
USP_EMENTAS_FILE = "usp_ementas.json"
USER_AGENT = "PPChat/1.0 (Academic Curriculum Assistant)"

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


def load_usp_curricula(processed_dir: Path) -> Dict[str, Curriculo]:
    path = processed_dir / USP_CURRICULA_FILE
    if not path.exists():
        return {}
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
        return {k: Curriculo.model_validate(v) for k, v in raw.items()}
    except Exception:
        return {}


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
            menu_html = r2.read().decode("iso-8859-1", errors="replace")
        ok = "webLogin.jsp" not in resp.geturl() and "usuário ou senha" not in _norm(html_out)
        return {"authenticated": ok, "menu_status": r2.status, "has_session_cookie": len(jar) > 0, "sso_url": "https://idpcafe.usp.br/idp/profile/SAML2/Redirect/SSO?execution=e1s1"}
    except Exception as exc:
        return {"authenticated": False, "reason": str(exc)}


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
