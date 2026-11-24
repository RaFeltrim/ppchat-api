import re
from functools import cached_property, lru_cache
from pathlib import Path
from typing import List, Sequence

from src.modules.ingestion.models.curriculum import Curriculo, Disciplina
from src.modules.ingestion.services.ingestion_pipeline import CURRICULUM_FILE, DOCUMENT_FILE
from src.modules.knowledge.services.curriculum_graph import CurriculumGraph
from src.modules.knowledge.services.ifsp_drive import load_ifsp_docs, search_ifsp_docs
from src.modules.knowledge.services.usp_jupiter import (
    CALENDARIO_ALUNO_ESPECIAL_2026_2027,
    USP_COURSES,
    build_all_institutes_mermaid,
    build_course_mermaid,
    compute_equivalences,
    fetch_usp_ementa,
    load_usp_aluno,
    load_usp_curricula,
)
from src.modules.shared.services.settings import get_settings

ABORDAGEM = {"teorica": "teórica", "pratica": "prática", "teorico_pratica": "teórico-prática"}
TIPO = {"obrigatoria": "obrigatória", "optativa": "optativa", "eletiva": "eletiva"}


def _hours(value: float) -> str:
    return f"{value:.1f}".replace(".", ",") + " h"


class KnowledgeBase:
    """Tudo que o modelo recebe sobre o curso: o PPC inteiro + o currículo estruturado com o grafo.

    O texto renderizado precisa ser byte a byte estável (nada de datas ou ordens aleatórias),
    porque ele forma o prefixo que fica no cache de prompt.
    """

    def __init__(self, processed_dir: Path):
        curriculum_path = processed_dir / CURRICULUM_FILE
        document_path = processed_dir / DOCUMENT_FILE
        if not curriculum_path.exists() or not document_path.exists():
            raise FileNotFoundError("Base não processada. Rode primeiro: python main.py ingest")

        self.processed_dir = processed_dir
        self.curriculo = Curriculo.model_validate_json(curriculum_path.read_text("utf-8"))
        self.document_text = document_path.read_text("utf-8")
        self.graph = CurriculumGraph(self.curriculo)
        self.ifsp_docs = load_ifsp_docs(processed_dir)
        self.usp_aluno = load_usp_aluno(processed_dir)
        self.usp_curricula = load_usp_curricula(processed_dir)
        self.usp_graphs = {k: CurriculumGraph(c) for k, c in self.usp_curricula.items()}
        self.usp_equivalences = compute_equivalences(self.curriculo, self.usp_curricula)
        self.mermaids = {
            "ifsp_bes": build_course_mermaid(self.curriculo, "ifsp_bes"),
            **{k: build_course_mermaid(c, k) for k, c in self.usp_curricula.items()},
        }
        self.all_institutes_mermaid = build_all_institutes_mermaid(self.curriculo, self.usp_curricula)

    def _names(self, codes: List[str]) -> str:
        return "; ".join(f"{self.graph.by_code[c].nome} ({c})" for c in codes) or "nenhuma"

    def _render_disciplina(self, d: Disciplina) -> str:
        a = self.graph.analysis[d.codigo]
        semestre = f"{d.semestre}º semestre" if d.semestre else "sem semestre fixo"
        lines = [
            f"### {d.nome} ({d.codigo})",
            f"- {semestre} · {TIPO[d.tipo]} · {d.aulas_semanais} aulas/semana · {d.total_aulas} aulas · "
            f"{_hours(d.carga_horaria_total)} (extensão: {_hours(d.carga_horaria_extensao)})",
            f"- Abordagem {ABORDAGEM[d.abordagem]} · laboratório: {'sim' if d.usa_laboratorio else 'não'}"
            + (f" · plano de ensino na [Página {d.pagina_plano_ensino}]" if d.pagina_plano_ensino else ""),
            f"- Pré-requisitos diretos: {self._names(d.pre_requisitos)}",
        ]
        if len(a.pre_requisitos_transitivos) > len(d.pre_requisitos):
            lines.append(f"- Base acumulada (todos os pré-requisitos indiretos): {self._names(a.pre_requisitos_transitivos)}")
        if a.profundidade > 0:
            lines.append(f"- Cadeia mais longa até ela: {' → '.join(a.cadeia_mais_longa)}")
        lines.append(f"- Libera diretamente: {self._names(a.libera_diretamente)}")
        if len(a.libera_transitivamente) > len(a.libera_diretamente):
            lines.append(f"- Trava, se reprovada, {len(a.libera_transitivamente)} disciplinas: {self._names(a.libera_transitivamente)}")
        lines.append(
            f"- Complexidade estimada: {a.indice_complexidade}/10 ({a.nivel_estimado}) · profundidade {a.profundidade}"
        )
        if d.grupos_conhecimento:
            lines.append(f"- Grupos de conhecimento: {', '.join(d.grupos_conhecimento)}")
        if d.topicos_principais:
            lines.append(f"- Tópicos: {'; '.join(d.topicos_principais)}")
        return "\n".join(lines)

    @cached_property
    def curriculum_context(self) -> str:
        c = self.curriculo
        disciplinas = sorted(c.disciplinas, key=lambda d: (d.semestre or 99, d.nome))
        parts = [
            f"# Currículo estruturado — {c.curso} ({c.campus}, vigência {c.vigencia})",
            f"Duração: {c.duracao_semestres} semestres · carga horária total: {_hours(c.carga_horaria_total_curso)}",
            "",
            "Dados extraídos do PPC. A complexidade estimada (0–10) NÃO é oficial: é calculada a partir "
            "da profundidade na cadeia de pré-requisitos (35%), do tamanho da base acumulada (25%), "
            "do semestre (25%) e da carga horária (15%).",
            "",
            "## Cadeia crítica (a sequência de pré-requisitos mais longa do curso)",
            " → ".join(f"{self.graph.by_code[x].nome} ({x})" for x in self.graph.critical_path),
            "",
            "## Disciplinas-gargalo (mais disciplinas dependem delas)",
            *(
                f"- {self.graph.by_code[x].nome} ({x}): trava {len(self.graph.analysis[x].libera_transitivamente)}"
                for x in self.graph.bottlenecks()
            ),
            "",
            "## Requisitos gerais para avançar e se formar",
            *(
                f"- {r.item}: {r.descricao}" + (f" [Página {r.pagina}]" if r.pagina else "")
                for r in c.requisitos_gerais
            ),
            "",
            "## Disciplinas",
            *(self._render_disciplina(d) + "\n" for d in disciplinas),
        ]
        return "\n".join(parts)

    def render_disciplinas(self, codes: List[str]) -> str:
        """Ficha das disciplinas que o usuário selecionou no chat (códigos desconhecidos são ignorados)."""
        parts = []
        for code in codes:
            if code in self.graph.by_code:
                parts.append(self._render_disciplina(self.graph.by_code[code]))
                continue
            for usp_key, g in self.usp_graphs.items():
                if code in g.by_code:
                    d = g.by_code[code]
                    parts.append(f"### {d.nome} ({d.codigo}) — {USP_COURSES[usp_key]['label']}\n- Semestre ideal: {d.semestre or 'Optativa'} · Carga horária: {_hours(d.carga_horaria_total)}\n- Pré-requisitos: {', '.join(d.pre_requisitos) or 'nenhum'}")
                    break
        return "\n\n".join(parts)

    def render_usp_equivalencias(self, question: str, focus: Sequence[str] = (), inst: str = "ifsp_bes") -> str:
        """Injeta contexto da USP/UFSCar São Carlos, ementas, equivalências e calendário de Aluno Especial."""
        if not self.usp_curricula:
            return ""
        q_low = question.lower()
        usp_codes = set(
            re.findall(
                r"\b(?:(?:SSC|SCC|SMA|SME|5500)\d{3,4}|(?:UFSCAR|ENC|PPGCC|LATO|IA27)-[A-Z0-9]+)\b",
                question.upper(),
            )
        )
        for fc in focus:
            if any(fc in g.by_code for g in self.usp_graphs.values()):
                usp_codes.add(fc.upper())

        triggers = (
            "usp", "caaso", "bsi", "bci", "bcc", "estat", "especial", "equival", "abater",
            "aproveit", "requerimento", "jupiter", "puxar", "ufscar", "externa", "disciplina",
            "materia", "curso", "fluxograma", "grade", "mermaid", "ppc", "seguranca", "movel",
            "mobile", "vvts", "teste", "calendario", "matricula", "edital",
        )
        if inst == "ifsp_bes" and not usp_codes and not any(t in q_low for t in triggers):
            return ""

        # Inclui automaticamente as disciplinas do estudante na USP + candidatas de pendências críticas
        student_usp_codes = {c.upper() for c in (self.usp_aluno or {}).get("status", {}).keys()}
        key_candidates = {"SCC0225", "SSC0524", "SSC0959", "SSC0547", "SSC0900", "SSC0901", "SSC0725", "UFSCAR-DMOV", "UFSCAR-ES2", "UFSCAR-SEGCIB", "UFSCAR-ASP"}
        if any(w in q_low for w in ("equival", "puxar", "especial", "aproveit", "abater", "ppc", "grade", "fluxograma", "falt", "pend", "rest")):
            usp_codes |= key_candidates
        usp_codes |= student_usp_codes

        lines = []
        if inst in self.usp_curricula:
            uc = self.usp_curricula[inst]
            meta = USP_COURSES.get(inst, {})
            lines.append(
                f"Curso selecionado na interface: {uc.curso} ({uc.campus}) — {len(uc.disciplinas)} disciplinas. "
                + (f"PPC: {meta.get('ppc_resumo', '')}" if meta.get("ppc_resumo") else "")
            )

        # Resumo oficial dos PPCs de todos os cursos externos disponíveis
        lines.append("PPCs oficiais indexados (USP ICMC & UFSCar São Carlos):")
        for k, meta in USP_COURSES.items():
            cur = self.usp_curricula.get(k)
            cnt = len(cur.disciplinas) if cur else 0
            lines.append(f"- `{k}` ({meta['label']}, {cnt} disc.): {meta.get('ppc_resumo', '')} | PPC URL: {meta.get('ppc_url', '')}")

        # Ementas oficiais de códigos USP/UFSCar citados ou cursados pelo aluno
        ordered_codes = sorted(student_usp_codes | (usp_codes - key_candidates)) + sorted(key_candidates & usp_codes)
        seen_em = set()
        for code in ordered_codes:
            if code in seen_em:
                continue
            seen_em.add(code)
            if len(seen_em) > 12:
                break
            try:
                em = fetch_usp_ementa(code, self.processed_dir)
                prog = em.get("programa") or em.get("programa_resumido") or ""
                obj = em.get("objetivos") or ""
                bib = em.get("bibliografia") or ""
                lines.append(
                    f"Ementa Oficial `{code}` ({em.get('titulo')}, {em.get('carga_horaria')}):\n"
                    + (f"- Objetivos: {obj[:500]}\n" if obj else "")
                    + (f"- Programa/Conteúdo: {prog[:1100]}\n" if prog else "")
                    + (f"- Bibliografia: {bib[:400]}\n" if bib else "")
                    + f"- URL: {em.get('url')}"
                )
            except Exception:
                pass

        # Equivalências: nunca oculta outros cursos; prioriza matérias pendentes/cursando e foco
        pending_priority = {"SCLPRDM", "SCLDMDM", "SCLVVTS", "SCLASEG", "SCLARSW", "SCLAPOO", "SCLMATC", "SCLRCO2", "SCLTAED", "SCLTTEC"}
        focus_set = {f.upper() for f in focus} | usp_codes | pending_priority
        prioritized = [e for e in self.usp_equivalences if e["ifsp_codigo"] in focus_set or e["usp_codigo"] in focus_set]
        if inst != "ifsp_bes":
            prioritized.sort(key=lambda e: (0 if e["usp_curso"] == inst else 1, 0 if e["equivalencia"] == "Alta" else 1, -e["similaridade_pct"]))
        seen_pairs = {(e["usp_curso"], e["usp_codigo"], e["ifsp_codigo"]) for e in prioritized}
        rest = [e for e in self.usp_equivalences if (e["usp_curso"], e["usp_codigo"], e["ifsp_codigo"]) not in seen_pairs]
        relevant = prioritized[:55] + rest[: max(0, 65 - len(prioritized[:55]))]

        if relevant:
            lines.append("Equivalências candidatas (USP ICMC & UFSCar São Carlos ↔ IFSP BES — todas as grades):")
            for e in relevant:
                lines.append(
                    f"- [{e['equivalencia']} {e['similaridade_pct']}% · CH {e['usp_ch']:.0f}h/{e['ifsp_ch']:.0f}h] "
                    f"{e['usp_curso_label']} `{e['usp_codigo']}` ({e['usp_nome']}) ↔ IFSP `{e['ifsp_codigo']}` ({e['ifsp_nome']})"
                )

        lines.append(CALENDARIO_ALUNO_ESPECIAL_2026_2027)
        return "\n".join(lines)

    def render_mermaid_fluxogramas(self, question: str, inst: str = "ifsp_bes") -> str:
        """Retorna fluxogramas Mermaid compactos por instituto de ensino para economia de tokens."""
        q_low = question.lower()
        triggers = (
            "fluxograma", "grade", "mermaid", "ppc", "curso", "outro", "instituto",
            "usp", "ufscar", "bsi", "bci", "bcc", "estat", "engenharia", "equival",
            "aproveit", "especial", "puxar", "materia", "disciplina", "comp", "falt",
        )
        if inst == "ifsp_bes" and not any(t in q_low for t in triggers):
            return ""
        # Sempre envia a visão completa dos institutos quando o assunto envolver grades/cursos/equivalências
        return self.all_institutes_mermaid

    def render_ifsp_docs(self, question: str) -> str:
        """Seleciona até 3 documentos relevantes do Drive IFSP (TokenOps)."""
        hits = search_ifsp_docs(self.ifsp_docs, question, limit=3)
        if not hits:
            return ""
        blocks = []
        for d in hits:
            body = d.get("text") or "(Planilha/formulário binário — indique o link oficial para download.)"
            blocks.append(f"### {d['name']}\nLink oficial: {d['url']}\n{body}")
        return "\n\n".join(blocks)

    def render_repo_evidences(self, question: str, focus: Sequence[str] = ()) -> str:
        """Lê READMEs, stacks e estrutura dos repositórios de disciplinas em Downloads/GitHub."""
        q_low = question.lower()
        triggers = (
            "repo", "reposit", "github", "projeto", "pratic", "codigo", "código",
            "evidenc", "equival", "abater", "aproveit", "disciplina", "usp", "ssc", "scl",
            "web", "mobile", "capacitor", "sibisc", "apoo",
        )
        if not focus and not any(t in q_low for t in triggers):
            return ""
        downloads = Path.home() / "Downloads"
        if not downloads.exists():
            return ""

        repo_dirs: List[Path] = []
        for folder in sorted(downloads.iterdir()):
            if not folder.is_dir():
                continue
            if (folder / ".git").is_dir():
                repo_dirs.append(folder)
            else:
                for sub in folder.iterdir():
                    if sub.is_dir() and (sub / ".git").is_dir():
                        repo_dirs.append(sub)

        q_terms = {w for w in re.findall(r"[a-z0-9]{3,}", q_low)} | {f.lower() for f in focus}
        scored: List[tuple[int, str]] = []
        skip = {".git", "node_modules", "__pycache__", ".venv", "venv", "dist", "build"}
        for rdir in repo_dirs:
            label = f"{rdir.parent.name}/{rdir.name}" if rdir.parent != downloads else rdir.name
            cfg = rdir / ".git" / "config"
            gh = ""
            if cfg.exists():
                m = re.search(r"url\s*=\s*(https://[^\s]+)", cfg.read_text(encoding="utf-8", errors="ignore"))
                if m:
                    gh = re.sub(r"https://[^@]+@", "https://", m.group(1).rstrip("/").removesuffix(".git"))
            readme = rdir / "README.md"
            hay = f"{label} {gh}".lower()
            if not any(k in hay for k in ("usp", "apoo", "web e mobile", "ifsp", "taed", "tcdd", "ttec", "redes", "ax2", "sustent")):
                continue
            readme_txt = readme.read_text(encoding="utf-8", errors="ignore")[:1800] if readme.exists() else ""
            manifests = []
            for p in rdir.rglob("*"):
                if any(part in skip for part in p.parts):
                    continue
                if p.is_file() and p.name.lower() in {"package.json", "capacitor.config.json", "requirements.txt", "pom.xml"}:
                    manifests.append(p.relative_to(rdir).as_posix())
                    if len(manifests) >= 6:
                        break
            block = (
                f"### {label}" + (f" ({gh})" if gh else "") + "\n"
                + (f"- Manifestos/config encontrados: {', '.join(manifests)}\n" if manifests else "")
                + (f"- README.md (resumo):\n{readme_txt}" if readme_txt else "")
            )
            full_hay = f"{hay} {readme_txt.lower()} {' '.join(manifests).lower()}"
            score = sum(1 for t in q_terms if t in full_hay)
            scored.append((score, block))
        scored.sort(key=lambda item: item[0], reverse=True)
        return "\n\n".join(b for _, b in scored)

    @cached_property
    def full_context(self) -> str:
        return (
            f"<curriculo_estruturado>\n{self.curriculum_context}\n</curriculo_estruturado>\n\n"
            f"<ppc_completo>\n{self.document_text}\n</ppc_completo>"
        )


@lru_cache
def get_knowledge_base() -> KnowledgeBase:
    return KnowledgeBase(get_settings().processed_dir)
