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
        "org": "usp",
        "instituto": "USP São Carlos — ICMC / CAASO",
        "label": "USP · BSI (CAASO)",
        "curso": "Bacharelado em Sistemas de Informação (BSI)",
        "campus": "USP São Carlos (ICMC / CAASO)",
        "codcg": "55",
        "codcur": "55051",
        "codhab": "4",
        "duracao_semestres": 8,
        "ppc_url": "https://web2.icmc.usp.br/SVGRAD/ppp/Projeto_Pedag%C3%B3gico_do_Curso_-_BSI_-_2026-2__2_-aprovado.pdf",
        "grade_url": "https://uspdigital.usp.br/jupiterweb/listarGradeCurricular?codcg=55&codcur=55051&codhab=4&tipo=N",
        "ppc_resumo": (
            "Noturno (seg–sex 18h–23h, sáb manhã/tarde), 50 vagas/ano. Duração ideal 8 semestres (mín 6, máx 12). "
            "CH total 3.881h (3.600h obrigatórias, 180h optativas eletivas, 30h AACs, >=10% extensão). "
            "Departamentos: SSC, SCC, SMA, SME e SEP/EESC. Certificados Especiais/Ênfases: Engenharia de Software, "
            "Desenvolvimento Web, Sistemas Computacionais Avançados e de Alto Desempenho, Ciência de Dados e TI/Negócios (FEA-RP)."
        ),
    },
    "usp_bci": {
        "key": "usp_bci",
        "org": "usp",
        "instituto": "USP São Carlos — ICMC / CAASO",
        "label": "USP · BCI / Comp. (CAASO)",
        "curso": "Bacharelado em Ciências de Computação (BCI/BCC)",
        "campus": "USP São Carlos (ICMC / CAASO)",
        "codcg": "55",
        "codcur": "55041",
        "codhab": "0",
        "duracao_semestres": 10,
        "ppc_url": "https://www.icmc.usp.br/graduacao/ciencias-de-computacao-bacharelado",
        "grade_url": "https://uspdigital.usp.br/jupiterweb/listarGradeCurricular?codcg=55&codcur=55041&codhab=0&tipo=N",
        "ppc_resumo": (
            "Integral, duração ideal 10 semestres (5 anos; mín 8, máx 15). CH total 4.732h (4.125h obrigatórias, "
            "360h optativas eletivas, 30h AACs, 452h extensão curricularizada, 600h estágio + 2 Projetos de Graduação/TCC). "
            "Ênfases/Certificados: IA, Ciência de Dados, Engenharia de Dados, Engenharia de Software, Robótica, Sistemas Embarcados e Alto Desempenho."
        ),
    },
    "usp_est": {
        "key": "usp_est",
        "org": "usp",
        "instituto": "USP São Carlos — ICMC / CAASO",
        "label": "USP · Estatística (CAASO)",
        "curso": "Bacharelado em Estatística e Ciência de Dados",
        "campus": "USP São Carlos (ICMC / CAASO)",
        "codcg": "55",
        "codcur": "55071",
        "codhab": "4",
        "duracao_semestres": 8,
        "ppc_url": "https://www.icmc.usp.br/graduacao/estatistica-bacharelado",
        "grade_url": "https://uspdigital.usp.br/jupiterweb/listarGradeCurricular?codcg=55&codcur=55071&codhab=4&tipo=N",
        "ppc_resumo": (
            "Noturno, 40 vagas/ano, duração ideal 8 semestres (4 anos; alinhado às diretrizes MEC >=3.000h e >=10% extensão). "
            "Núcleo em matemática, probabilidade, inferência estatística, computação, aprendizado de máquina e visualização de dados."
        ),
    },
    "ufscar_bcc": {
        "key": "ufscar_bcc",
        "org": "ufscar",
        "instituto": "UFSCar São Carlos — DC / CCET",
        "label": "UFSCar · Ciência da Comp. (BCC)",
        "curso": "Bacharelado em Ciência da Computação (BCC)",
        "campus": "UFSCar São Carlos (DC / CCET)",
        "codcg": "UFSCAR",
        "codcur": "BCC",
        "codhab": "2025",
        "duracao_semestres": 8,
        "ppc_url": "https://www.prograd.ufscar.br/pt-br/assets/arquivos/cursos/cursos-oferecidos/ciencias-da-computacao/ppc_bel-ciencia_da_computacao_2025.pdf",
        "grade_url": "https://www.prograd.ufscar.br/pt-br/cursos/cursos-oferecidos/ciencia-da-computacao/sao-carlos",
        "ppc_resumo": (
            "Integral (matutino/vespertino), 60 vagas, 8 semestres, CH total 3.240h (1.830h obrigatórias [1.770h T/P + 60h Ext], "
            "540h optativas de trilha [9x 60h nos semestres 5–7], 360h Estágio ou TCC no 8º sem, 300h ACE/PIE/ACIEPE, 210h ACs). "
            "Optativas fortes para BES: Engenharia de Software 2 (testes), Arquitetura de Software e Padrões, Desenvolvimento Móvel, Segurança Cibernética e DevOps."
        ),
    },
    "ufscar_enc": {
        "key": "ufscar_enc",
        "org": "ufscar",
        "instituto": "UFSCar São Carlos — DC / CCET",
        "label": "UFSCar · Eng. de Computação (ENC)",
        "curso": "Bacharelado em Engenharia de Computação (ENC)",
        "campus": "UFSCar São Carlos (DC / CCET)",
        "codcg": "UFSCAR",
        "codcur": "ENC",
        "codhab": "2025",
        "duracao_semestres": 10,
        "ppc_url": "https://www.prograd.ufscar.br/pt-br/assets/arquivos/cursos/cursos-oferecidos/engenharia-de-computacao/PPC_EC_2019.pdf",
        "grade_url": "https://www.prograd.ufscar.br/pt-br/cursos/cursos-oferecidos/engenharia-de-computacao",
        "ppc_resumo": (
            "Integral (matutino/vespertino), 30 vagas, 10 semestres, CH total 3.660h. Matriz 2025 combina Matemática, Física, Eletrônica, "
            "Computação, Engenharia de Software 1, Sistemas Operacionais, Redes, Banco de Dados, IA, Sistemas Distribuídos, Embarcados, "
            "180h Estágio + TCC 1 e 2 + ACEs."
        ),
    },
    "ufscar_ia_pos": {
        "key": "ufscar_ia_pos",
        "org": "ufscar",
        "instituto": "UFSCar São Carlos — DC / CCET & PPGCC",
        "label": "UFSCar · IA (2027) & Pós/Especialização",
        "curso": "IA (2027) · PPGCC (CAPES 5) · Especialização Dev. Software",
        "campus": "UFSCar São Carlos (DC / PPGCC)",
        "codcg": "UFSCAR",
        "codcur": "IA-POS",
        "codhab": "2027",
        "duracao_semestres": 4,
        "ppc_url": "https://www.ppgcc.ufscar.br/pt-br/processo-seletivo/aluno-especial",
        "grade_url": "https://www.latosensudc.ufscar.br/inscricoes-abertas-para-a-turma-2027",
        "ppc_resumo": (
            "Reúne: (1) Novo Bacharelado em Inteligência Artificial (previsto 2027 no CCET/São Carlos); "
            "(2) Mestrado/Doutorado PPGCC (CAPES 5; 47 vagas 2027/1 em ES, AMPLN, BD, CCH, SDARC, VC, SAR; aceita graduando no penúltimo ano ou último ano como Aluno Especial); "
            "(3) Especialização Lato Sensu DC 'Computação – Desenvolvimento de Software' (inscrições 01/10–30/11/2026, início 13/02/2027: Ágil, DevOps, Arquitetura, Testes Automatizados, ML e IA)."
        ),
    },
}

CALENDARIO_ALUNO_ESPECIAL_2026_2027 = """Calendário e Regras Oficiais — Aluno Especial (USP ICMC & UFSCar São Carlos):
1. USP São Carlos (ICMC — Graduação, Resolução CoG 3757):
   - Máximo de 2 disciplinas por semestre; proibido cursar disciplinas do 1º ano; códigos SCC, SMA, SME e SSC; dependente de vagas remanescentes após matrícula regular.
   - Documentos padrão: RG, certificado de conclusão do Ensino Médio e histórico escolar completo (com reprovações).
   - 2º semestre/2026 (referência verificada): inscrições ocorreram em 27–28/07/2026 via formulário do Serviço de Graduação (icmc.usp.br/graduacao/ingresso | grad@icmc.usp.br).
   - 1º semestre/2027 (Calendário Escolar PRG-USP): aulas começam em 01/03/2027 e terminam em 07/07/2027; janela de Estudante Especial no ICMC abre tipicamente na 2ª quinzena de fevereiro (após as interações de matrícula regular; acompanhar icmc.usp.br/graduacao/ingresso a partir de 09–26/02/2027).
   - 2º semestre/2027 (Calendário Escolar PRG-USP): aulas começam em 02/08/2027 e terminam em 13/12/2027; janela de Estudante Especial tipicamente nos últimos dias úteis de julho (acompanhar a partir de 19–30/07/2027).
2. UFSCar São Carlos (Graduação ProGrad/DiGRA — Resolução CoG nº 554/2026 & Administrativo 2027):
   - 2027/1 (Cursos Semestrais):
     * 29/01/2027: Chefias de Departamento indicam vagas para o Edital de Estudante Especial.
     * 05/02/2027: Publicação oficial do Edital de "Estudante Especial" (2027/1) pela DiGRA/ProGrad (prograd.ufscar.br).
     * 10–12/02/2027 (inscrição regular) e 17–18/02/2027 (ajuste); 23/02/2027 deferimento final; 01/03/2027 início das aulas (término 03/07/2027).
     * Atenção: edital de Estudante Especial na graduação da UFSCar atende alunos com vínculo em IES conveniadas ou portadores de diploma (conferir convênio/cláusulas no edital de 05/02/2027).
   - 2027/2 (Cursos Semestrais):
     * 02/07/2027: Indicação de vagas; 08/07/2027: Publicação do Edital de "Estudante Especial" (2027/2); 02/08/2027 início das aulas.
   - PPGCC UFSCar (Mestrado/Pós Stricto Sensu — Aluno Especial):
     * Aceita graduandos cursando o penúltimo ano ou superior da graduação com bom rendimento (ppgcc.ufscar.br/pt-br/processo-seletivo/aluno-especial). Inscrição online semestralmente (jan–fev para 1º sem; jun–início ago para 2º sem).
   - Especialização Lato Sensu DC-UFSCar (Desenvolvimento de Software — Turma 2027):
     * Inscrições abertas de 01/10/2026 a 30/11/2026 (urgente — fecha em 30/11/2026), aceitos em 05/12/2026, aulas a partir de 13/02/2027 (latosensudc.ufscar.br)."""

UFSCAR_LOCAL_EMENTAS = {
    "UFSCAR-MD": {
        "codigo": "UFSCAR-MD",
        "titulo": "UFSCAR-MD - Matemática Discreta (BCC UFSCar)",
        "carga_horaria": "60 h",
        "objetivos": "Desenvolver raciocínio lógico-matemático, técnicas de demonstração e modelagem discreta aplicadas à Computação.",
        "programa": "Lógica proposicional e de predicados; técnicas de demonstração e indução matemática; recursão; conjuntos, relações e funções; teoria dos grafos e árvores; combinatória e álgebra booleana.",
        "bibliografia": "ROSEN, K. H. Matemática Discreta e suas Aplicações.",
        "url": "https://www.prograd.ufscar.br/pt-br/assets/arquivos/cursos/cursos-oferecidos/ciencias-da-computacao/ppc_bel-ciencia_da_computacao_2025.pdf",
    },
    "UFSCAR-ES1": {
        "codigo": "UFSCAR-ES1",
        "titulo": "UFSCAR-ES1 - Engenharia de Software 1 (BCC/ENC UFSCar)",
        "carga_horaria": "60 h",
        "objetivos": "Capacitar o aluno nos fundamentos de engenharia de requisitos, análise e projeto orientado a objetos e processos de software.",
        "programa": "Ciclo de vida e processos de software; métodos ágeis; elicitação, análise e especificação de requisitos; diagramas UML (casos de uso, classes, sequência, atividades, estados); princípios de projeto OO; introdução a testes.",
        "bibliografia": "SOMMERVILLE, I. Engenharia de Software; LARMAN, C. Utilizando UML e Padrões.",
        "url": "https://www.prograd.ufscar.br/pt-br/assets/arquivos/cursos/cursos-oferecidos/ciencias-da-computacao/ppc_bel-ciencia_da_computacao_2025.pdf",
    },
    "UFSCAR-ES2": {
        "codigo": "UFSCAR-ES2",
        "titulo": "UFSCAR-ES2 - Engenharia de Software 2 (BCC UFSCar Optativa 5º Sem)",
        "carga_horaria": "60 h",
        "objetivos": "Aprofundar técnicas de verificação, validação, teste de software, garantia de qualidade e evolução de sistemas.",
        "programa": "Qualidade de produto e processo; verificação e validação (VV&T); inspeção e revisão técnica; teste funcional, estrutural e baseado em defeitos; testes de unidade, integração, sistema, regressão e aceitação; TDD; ferramentas de automação de testes.",
        "bibliografia": "DELAMARO, M. E. et al. Introdução ao Teste de Software; SOMMERVILLE, I. Engenharia de Software.",
        "url": "https://www.prograd.ufscar.br/pt-br/assets/arquivos/cursos/cursos-oferecidos/ciencias-da-computacao/ppc_bel-ciencia_da_computacao_2025.pdf",
    },
    "UFSCAR-POOA": {
        "codigo": "UFSCAR-POOA",
        "titulo": "UFSCAR-POOA - Programação Orientada a Objetos Avançada (BCC UFSCar)",
        "carga_horaria": "60 h",
        "objetivos": "Aplicar princípios avançados de análise, projeto e implementação orientada a objetos com padrões de projeto.",
        "programa": "Modelagem UML avançada (classes, sequência, comunicação, estados); princípios de responsabilidade (GRASP e SOLID); padrões de projeto GoF (criacionais, estruturais e comportamentais); persistência objeto-relacional; testes.",
        "bibliografia": "GAMMA, E. et al. Padrões de Projeto; LARMAN, C. Utilizando UML e Padrões.",
        "url": "https://www.prograd.ufscar.br/pt-br/assets/arquivos/cursos/cursos-oferecidos/ciencias-da-computacao/ppc_bel-ciencia_da_computacao_2025.pdf",
    },
    "UFSCAR-ASP": {
        "codigo": "UFSCAR-ASP",
        "titulo": "UFSCAR-ASP - Arquitetura de Software e Padrões (BCC UFSCar)",
        "carga_horaria": "60 h",
        "objetivos": "Conceber, documentar e avaliar arquiteturas de software usando estilos, padrões e atributos de qualidade.",
        "programa": "Conceitos e terminologia de arquitetura de software; propriedades e atributos de qualidade; estilos arquiteturais (camadas, pipes-and-filters, microsserviços, orientada a eventos, SOA); padrões arquiteturais; decisões, ADRs, visões e avaliação arquitetural (ATAM).",
        "bibliografia": "BASS, L.; CLEMENTS, P.; KAZMAN, R. Software Architecture in Practice.",
        "url": "https://www.prograd.ufscar.br/pt-br/assets/arquivos/cursos/cursos-oferecidos/ciencias-da-computacao/ppc_bel-ciencia_da_computacao_2025.pdf",
    },
    "UFSCAR-DMOV": {
        "codigo": "UFSCAR-DMOV",
        "titulo": "UFSCAR-DMOV - Desenvolvimento Móvel (BCC UFSCar Optativa 7º Sem)",
        "carga_horaria": "60 h",
        "objetivos": "Desenvolver aplicações para dispositivos móveis nativas e multiplataforma integradas a WebServices.",
        "programa": "Introdução à computação móvel; arquiteturas de plataformas móveis; interface gráfica e componentes visuais; persistência local em arquivos e bancos de dados; acesso a sensores/hardware e APIs do dispositivo; sincronização e comunicação HTTP/WebServices; abordagens híbridas e multiplataforma.",
        "bibliografia": "LECHETA, R. R. Google Android; documentações oficiais Android/Flutter/Capacitor.",
        "url": "https://www.prograd.ufscar.br/pt-br/assets/arquivos/cursos/cursos-oferecidos/ciencias-da-computacao/ppc_bel-ciencia_da_computacao_2025.pdf",
    },
    "UFSCAR-SEGCIB": {
        "codigo": "UFSCAR-SEGCIB",
        "titulo": "UFSCAR-SEGCIB - Segurança Cibernética (BCC UFSCar Optativa 6º Sem)",
        "carga_horaria": "60 h",
        "objetivos": "Analisar vulnerabilidades, aplicar mecanismos criptográficos e realizar auditoria e proteção de sistemas e redes.",
        "programa": "Fundamentos de segurança da informação; confidencialidade, integridade e disponibilidade; criptografia simétrica e assimétrica; funções hash e certificados digitais (PKI); autenticação e controle de acesso; auditoria e análise de riscos; políticas de segurança; segurança em redes, firewalls, IDS/IPS e testes de invasão.",
        "bibliografia": "STALLINGS, W. Criptografia e Segurança de Redes.",
        "url": "https://www.prograd.ufscar.br/pt-br/assets/arquivos/cursos/cursos-oferecidos/ciencias-da-computacao/ppc_bel-ciencia_da_computacao_2025.pdf",
    },
    "UFSCAR-DEVOPS": {
        "codigo": "UFSCAR-DEVOPS",
        "titulo": "UFSCAR-DEVOPS - DevOps (BCC UFSCar Optativa 7º Sem)",
        "carga_horaria": "60 h",
        "objetivos": "Integrar desenvolvimento, testes automatizados, entrega contínua e operação em infraestrutura moderna.",
        "programa": "Cultura DevOps; controle de versão e fluxos CI/CD; automação de build e testes; containerização e orquestração; infraestrutura como código; observabilidade, métricas e tecnologias emergentes.",
        "bibliografia": "KIM, G. et al. The DevOps Handbook.",
        "url": "https://www.prograd.ufscar.br/pt-br/assets/arquivos/cursos/cursos-oferecidos/ciencias-da-computacao/ppc_bel-ciencia_da_computacao_2025.pdf",
    },
    "PPGCC-VVTS": {
        "codigo": "PPGCC-VVTS",
        "titulo": "PPGCC-VVTS - Verificação, Validação e Teste de Software (PPGCC UFSCar)",
        "carga_horaria": "60 h",
        "objetivos": "Estudo avançado de técnicas, critérios, automação e pesquisa em verificação, validação e teste de software.",
        "programa": "Qualidade de processo/produto; verificação estática; critérios funcionais, estruturais e baseados em mutação; testes unitário, integração, sistema, regressão e aceitação; TDD e ferramentas.",
        "bibliografia": "DELAMARO, M. E. et al. Introdução ao Teste de Software.",
        "url": "https://www.ppgcc.ufscar.br/pt-br/processo-seletivo/aluno-especial",
    },
    "PPGCC-SEGCIB": {
        "codigo": "PPGCC-SEGCIB",
        "titulo": "PPGCC-SEGCIB - Segurança de Sistemas e Redes (PPGCC UFSCar)",
        "carga_horaria": "60 h",
        "objetivos": "Fundamentos e prática em auditoria, criptografia, análise de riscos e segurança em sistemas computacionais.",
        "programa": "Políticas de segurança; criptografia e infraestrutura de chaves; análise de vulnerabilidades e riscos; auditoria de sistemas; segurança em aplicações Web e redes; testes de invasão.",
        "bibliografia": "STALLINGS, W. Criptografia e Segurança de Redes.",
        "url": "https://www.ppgcc.ufscar.br/pt-br/processo-seletivo/aluno-especial",
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


def _make_disc(
    code: str,
    nome: str,
    semestre: Optional[int],
    ch: float,
    tipo: str = "obrigatoria",
    pre: Optional[List[str]] = None,
    topicos: Optional[List[str]] = None,
    grupo: str = "UFSCar DC/CCET",
    ext: float = 0.0,
) -> Disciplina:
    pratica = "laboratorio" in _norm(nome) or "experimental" in _norm(nome) or tipo == "optativa"
    return Disciplina(
        codigo=code,
        nome=nome.upper(),
        semestre=semestre,
        tipo=tipo,
        aulas_semanais=max(2, round(ch / 15)),
        total_aulas=max(30, round(ch)),
        carga_horaria_ensino=max(0.0, ch - ext),
        carga_horaria_extensao=ext,
        carga_horaria_total=ch,
        abordagem="teorico_pratica" if pratica else "teorica",
        usa_laboratorio=pratica or "programacao" in _norm(nome) or "dados" in _norm(nome) or "redes" in _norm(nome),
        pre_requisitos=pre or [],
        grupos_conhecimento=[grupo],
        topicos_principais=topicos or [],
        pagina_plano_ensino=None,
    )


def _ppc_requisitos_for(key: str) -> List[RequisitoGeral]:
    meta = USP_COURSES.get(key, {})
    reqs = []
    if meta.get("ppc_resumo"):
        reqs.append(
            RequisitoGeral(
                item=f"Estrutura PPC ({meta.get('curso', key)})",
                descricao=meta["ppc_resumo"] + (f" | PPC: {meta['ppc_url']}" if meta.get("ppc_url") else ""),
                pagina=None,
            )
        )
    if meta.get("org") == "usp":
        reqs.append(
            RequisitoGeral(
                item="Aluno Especial (ICMC/USP — Resolução CoG 3757)",
                descricao="Até 2 disciplinas/semestre (vedado 1º ano; códigos SCC/SMA/SME/SSC). 2º sem/2026: 27–28/07/2026; 2027/1 aulas 01/03–07/07/2027 (janela típica fev); 2027/2 aulas 02/08–13/12/2027 (janela típica final de jul).",
                pagina=None,
            )
        )
    elif meta.get("org") == "ufscar":
        reqs.append(
            RequisitoGeral(
                item="Aluno Especial (UFSCar São Carlos — CoG 554/2026)",
                descricao="Graduação ProGrad/DiGRA: Edital 2027/1 em 05/02/2027 (aulas 01/03–03/07/2027) e 2027/2 em 08/07/2027 (aulas 02/08–15/12/2027). PPGCC Stricto Sensu: graduando penúltimo/último ano. Especialização Dev. Software 2027: até 30/11/2026.",
                pagina=None,
            )
        )
    reqs.append(
        RequisitoGeral(
            item="Aproveitamento de Estudos no IFSP",
            descricao="Equivalência >= 75%/80% de carga horária e conteúdo programático mediante requerimento no SUAP (vedado para dependências).",
            pagina=47,
        )
    )
    return reqs


def build_ufscar_curricula() -> Dict[str, Curriculo]:
    """Constrói as matrizes oficiais 2025/2026–2027 dos cursos da UFSCar São Carlos."""
    bcc_discs = [
        _make_disc("UFSCAR-CDI1", "CÁLCULO DIFERENCIAL E INTEGRAL 1", 1, 90),
        _make_disc("UFSCAR-MD", "MATEMÁTICA DISCRETA", 1, 60, topicos=["Lógica formal", "Demonstração e indução", "Relações e conjuntos", "Teoria dos grafos", "Combinatória"]),
        _make_disc("UFSCAR-IPA", "INTRODUÇÃO AO PENSAMENTO ALGORÍTMICO", 1, 30),
        _make_disc("UFSCAR-CAP", "CONSTRUÇÃO DE ALGORITMOS E PROGRAMAÇÃO", 1, 120),
        _make_disc("UFSCAR-LD", "LÓGICA DIGITAL", 1, 90),
        _make_disc("UFSCAR-GA", "GEOMETRIA ANALÍTICA", 2, 60),
        _make_disc("UFSCAR-EB", "ESTATÍSTICA BÁSICA", 2, 60),
        _make_disc("UFSCAR-LM", "LÓGICA MATEMÁTICA", 2, 60, topicos=["Lógica proposicional", "Lógica de predicados", "Dedução natural"]),
        _make_disc("UFSCAR-AED1", "ALGORITMOS E ESTRUTURAS DE DADOS 1", 2, 60, pre=["UFSCAR-CAP"]),
        _make_disc("UFSCAR-POO", "PROGRAMAÇÃO ORIENTADA A OBJETOS", 2, 60, pre=["UFSCAR-CAP"]),
        _make_disc("UFSCAR-AOC1", "ARQUITETURA E ORGANIZAÇÃO DE COMPUTADORES 1", 2, 90, pre=["UFSCAR-LD"]),
        _make_disc("UFSCAR-CDS", "CÁLCULO DIFERENCIAL E SÉRIES", 3, 60, pre=["UFSCAR-CDI1"]),
        _make_disc("UFSCAR-AED2", "ALGORITMOS E ESTRUTURAS DE DADOS 2", 3, 60, pre=["UFSCAR-AED1"]),
        _make_disc("UFSCAR-ORI", "ORGANIZAÇÃO E RECUPERAÇÃO DA INFORMAÇÃO", 3, 60, pre=["UFSCAR-AED1"]),
        _make_disc("UFSCAR-SO", "SISTEMAS OPERACIONAIS", 3, 90, pre=["UFSCAR-AOC1"]),
        _make_disc("UFSCAR-CS", "COMPUTAÇÃO E SOCIEDADE", 3, 60, ext=60),
        _make_disc("UFSCAR-MC", "METODOLOGIA CIENTÍFICA", 3, 60),
        _make_disc("UFSCAR-AL1", "ÁLGEBRA LINEAR 1", 4, 60, pre=["UFSCAR-GA"]),
        _make_disc("UFSCAR-PAA", "PROJETO E ANÁLISE DE ALGORITMOS", 4, 60, pre=["UFSCAR-AED2"], topicos=["Análise de complexidade", "Paradigmas de algoritmos", "Grafos"]),
        _make_disc("UFSCAR-IHC", "INTERAÇÃO HUMANO-COMPUTADOR", 4, 60, pre=["UFSCAR-CAP"]),
        _make_disc("UFSCAR-ES1", "ENGENHARIA DE SOFTWARE 1", 4, 60, pre=["UFSCAR-POO"], topicos=["Processos de software", "Requisitos", "UML", "Análise e projeto OO"]),
        _make_disc("UFSCAR-BD", "BANCO DE DADOS", 4, 60, pre=["UFSCAR-AED1"]),
        _make_disc("UFSCAR-IA", "INTELIGÊNCIA ARTIFICIAL", 4, 60, pre=["UFSCAR-AED1"]),
        _make_disc("UFSCAR-CN", "CÁLCULO NUMÉRICO", 5, 60, pre=["UFSCAR-CDI1", "UFSCAR-GA", "UFSCAR-CAP"]),
        _make_disc("UFSCAR-RC", "REDES DE COMPUTADORES", 5, 60, pre=["UFSCAR-SO"], topicos=["Protocolos TCP/IP", "Infraestrutura e serviços de rede", "Segurança e firewall"]),
        _make_disc("UFSCAR-PAA2", "PROJETO E ANÁLISE DE ALGORITMOS 2", 5, 60, tipo="optativa", pre=["UFSCAR-PAA"], topicos=["Programação competitiva", "Paradigmas de projeto", "Estruturas avançadas"]),
        _make_disc("UFSCAR-POOA", "PROGRAMAÇÃO ORIENTADA A OBJETOS AVANÇADA", 5, 60, tipo="optativa", pre=["UFSCAR-AED1", "UFSCAR-POO"], topicos=["UML", "Padrões GoF", "GRASP/SOLID", "Persistência"]),
        _make_disc("UFSCAR-DSW1", "DESENVOLVIMENTO DE SOFTWARE PARA WEB 1", 5, 60, tipo="optativa", pre=["UFSCAR-BD"]),
        _make_disc("UFSCAR-ES2", "ENGENHARIA DE SOFTWARE 2", 5, 60, tipo="optativa", pre=["UFSCAR-ES1"], topicos=["Verificação e validação", "Testes de unidade, integração e sistema", "Regressão e TDD", "Qualidade e revisão"]),
        _make_disc("UFSCAR-PIBD", "PROJETO E IMPLEMENTAÇÃO DE BANCO DE DADOS", 5, 60, tipo="optativa", pre=["UFSCAR-BD"]),
        _make_disc("UFSCAR-AM1", "APRENDIZADO DE MÁQUINA 1", 5, 60, tipo="optativa", pre=["UFSCAR-IA", "UFSCAR-EB"]),
        _make_disc("UFSCAR-SD", "SISTEMAS DISTRIBUÍDOS", 5, 60, tipo="optativa", pre=["UFSCAR-SO"]),
        _make_disc("UFSCAR-PPD", "PROGRAMAÇÃO PARALELA E DISTRIBUÍDA", 6, 60, pre=["UFSCAR-SO"]),
        _make_disc("UFSCAR-TC", "TEORIA DA COMPUTAÇÃO", 6, 60, pre=["UFSCAR-MD"]),
        _make_disc("UFSCAR-PLP", "PARADIGMAS DE LINGUAGENS DE PROGRAMAÇÃO", 6, 60, tipo="optativa", pre=["UFSCAR-PAA"]),
        _make_disc("UFSCAR-DSW2", "DESENVOLVIMENTO DE SOFTWARE PARA WEB 2", 6, 60, tipo="optativa", pre=["UFSCAR-DSW1"]),
        _make_disc("UFSCAR-ASP", "ARQUITETURA DE SOFTWARE E PADRÕES", 6, 60, tipo="optativa", pre=["UFSCAR-ES2"], topicos=["Estilos arquiteturais", "Atributos de qualidade", "Documentação e avaliação arquitetural", "Microsserviços"]),
        _make_disc("UFSCAR-BDCD", "BANCO DE DADOS PARA CIÊNCIA DE DADOS", 6, 60, tipo="optativa", pre=["UFSCAR-PIBD"]),
        _make_disc("UFSCAR-AM2", "APRENDIZADO DE MÁQUINA 2", 6, 60, tipo="optativa", pre=["UFSCAR-AM1"]),
        _make_disc("UFSCAR-SEGCIB", "SEGURANÇA CIBERNÉTICA", 6, 60, tipo="optativa", pre=["UFSCAR-SO", "UFSCAR-AOC1"], topicos=["Segurança da informação", "Criptografia e PKI", "Auditoria e riscos", "Firewalls e testes de invasão"]),
        _make_disc("UFSCAR-CC", "CONSTRUÇÃO DE COMPILADORES", 7, 60, pre=["UFSCAR-TC", "UFSCAR-CAP"]),
        _make_disc("UFSCAR-DMOV", "DESENVOLVIMENTO MÓVEL", 7, 60, tipo="optativa", pre=["UFSCAR-DSW2"], topicos=["Computação móvel", "Interface gráfica", "Aplicações nativas e multiplataforma", "Persistência de dados", "Hardware e WebServices"]),
        _make_disc("UFSCAR-DEVOPS", "DEVOPS", 7, 60, tipo="optativa", pre=["UFSCAR-ES2"], topicos=["CI/CD", "Automação de testes", "Containers", "Tecnologias emergentes"]),
        _make_disc("UFSCAR-PLN", "PROCESSAMENTO DE LINGUAGEM NATURAL", 7, 60, tipo="optativa", pre=["UFSCAR-IA"]),
        _make_disc("UFSCAR-VC", "VISÃO COMPUTACIONAL", 7, 60, tipo="optativa", pre=["UFSCAR-AM2"]),
        _make_disc("UFSCAR-PSCE", "PROJETO DE SISTEMAS COMPUTACIONAIS EMBARCADOS", 7, 60, tipo="optativa", pre=["UFSCAR-AOC1"]),
        _make_disc("UFSCAR-AAD", "ARQUITETURAS DE ALTO DESEMPENHO", 7, 60, tipo="optativa", pre=["UFSCAR-AOC1"]),
        _make_disc("UFSCAR-EST", "ESTÁGIO EM COMPUTAÇÃO", 8, 360),
        _make_disc("UFSCAR-TCC", "TRABALHO DE CONCLUSÃO DE CURSO", 8, 360),
    ]

    enc_discs = [
        _make_disc("ENC-CDI1", "CÁLCULO DIFERENCIAL E INTEGRAL 1", 1, 90, grupo="UFSCar ENC"),
        _make_disc("ENC-GA", "GEOMETRIA ANALÍTICA", 1, 60, grupo="UFSCar ENC"),
        _make_disc("ENC-CAP", "CONSTRUÇÃO DE ALGORITMOS E PROGRAMAÇÃO", 1, 120, grupo="UFSCar ENC"),
        _make_disc("ENC-IPA", "INTRODUÇÃO AO PENSAMENTO ALGORÍTMICO", 1, 30, grupo="UFSCar ENC"),
        _make_disc("ENC-LD", "LÓGICA DIGITAL", 1, 90, grupo="UFSCar ENC"),
        _make_disc("ENC-C2", "CÁLCULO 2", 2, 60, pre=["ENC-CDI1"], grupo="UFSCar ENC"),
        _make_disc("ENC-AL1", "ÁLGEBRA LINEAR 1", 2, 60, pre=["ENC-GA"], grupo="UFSCar ENC"),
        _make_disc("ENC-FIS1", "FÍSICA 1", 2, 60, grupo="UFSCar ENC"),
        _make_disc("ENC-FEA", "FÍSICA EXPERIMENTAL A", 2, 60, grupo="UFSCar ENC"),
        _make_disc("ENC-AED1", "ALGORITMOS E ESTRUTURAS DE DADOS 1", 2, 60, pre=["ENC-CAP"], grupo="UFSCar ENC"),
        _make_disc("ENC-POO", "PROGRAMAÇÃO ORIENTADA A OBJETOS", 2, 60, pre=["ENC-CAP"], grupo="UFSCar ENC"),
        _make_disc("ENC-SDIG", "SISTEMAS DIGITAIS", 2, 60, pre=["ENC-LD"], grupo="UFSCar ENC"),
        _make_disc("ENC-C3", "CÁLCULO 3", 3, 60, pre=["ENC-C2"], grupo="UFSCar ENC"),
        _make_disc("ENC-SED", "SÉRIES E EQUAÇÕES DIFERENCIAIS", 3, 60, pre=["ENC-CDI1"], grupo="UFSCar ENC"),
        _make_disc("ENC-FIS3", "FÍSICA 3", 3, 60, pre=["ENC-FIS1"], grupo="UFSCar ENC"),
        _make_disc("ENC-FEB", "FÍSICA EXPERIMENTAL B", 3, 60, grupo="UFSCar ENC"),
        _make_disc("ENC-AED2", "ALGORITMOS E ESTRUTURAS DE DADOS 2", 3, 60, pre=["ENC-AED1"], grupo="UFSCar ENC"),
        _make_disc("ENC-AOC1", "ARQUITETURA E ORGANIZAÇÃO DE COMPUTADORES 1", 3, 90, pre=["ENC-LD"], grupo="UFSCar ENC"),
        _make_disc("ENC-SEM1", "SEMINÁRIOS 1", 3, 30, ext=30, grupo="UFSCar ENC"),
        _make_disc("ENC-EB", "ESTATÍSTICA BÁSICA", 4, 60, grupo="UFSCar ENC"),
        _make_disc("ENC-CN", "CÁLCULO NUMÉRICO", 4, 60, pre=["ENC-CDI1", "ENC-GA", "ENC-CAP"], grupo="UFSCar ENC"),
        _make_disc("ENC-CE", "CIRCUITOS ELÉTRICOS", 4, 60, pre=["ENC-SED"], grupo="UFSCar ENC"),
        _make_disc("ENC-PAA", "PROJETO E ANÁLISE DE ALGORITMOS", 4, 60, pre=["ENC-AED1"], grupo="UFSCar ENC"),
        _make_disc("ENC-AOC2", "ARQUITETURA E ORGANIZAÇÃO DE COMPUTADORES 2", 4, 60, pre=["ENC-AOC1"], grupo="UFSCar ENC"),
        _make_disc("ENC-ES1", "ENGENHARIA DE SOFTWARE 1", 4, 60, pre=["ENC-POO"], grupo="UFSCar ENC"),
        _make_disc("ENC-SDIN", "SISTEMAS DINÂMICOS", 4, 60, pre=["ENC-SED", "ENC-FIS3", "ENC-FEB"], grupo="UFSCar ENC"),
        _make_disc("ENC-EL1", "CIRCUITOS ELETRÔNICOS 1", 5, 90, pre=["ENC-CE"], grupo="UFSCar ENC"),
        _make_disc("ENC-ORI", "ORGANIZAÇÃO E RECUPERAÇÃO DA INFORMAÇÃO", 5, 60, pre=["ENC-AED1"], grupo="UFSCar ENC"),
        _make_disc("ENC-SO", "SISTEMAS OPERACIONAIS", 5, 90, pre=["ENC-AOC1"], grupo="UFSCar ENC"),
        _make_disc("ENC-CTR1", "CONTROLE 1", 5, 90, pre=["ENC-SDIN"], grupo="UFSCar ENC"),
        _make_disc("ENC-PSD", "PROCESSAMENTO DE SINAIS DIGITAIS", 5, 90, pre=["ENC-CDI1", "ENC-GA", "ENC-AL1", "ENC-CAP"], grupo="UFSCar ENC"),
        _make_disc("ENC-EL2", "CIRCUITOS ELETRÔNICOS 2", 6, 90, pre=["ENC-EL1"], grupo="UFSCar ENC"),
        _make_disc("ENC-IA", "INTELIGÊNCIA ARTIFICIAL", 6, 60, pre=["ENC-AED1"], grupo="UFSCar ENC"),
        _make_disc("ENC-BD", "BANCO DE DADOS", 6, 60, pre=["ENC-AED1"], grupo="UFSCar ENC"),
        _make_disc("ENC-CTR2", "CONTROLE 2", 6, 90, pre=["ENC-CTR1"], grupo="UFSCar ENC"),
        _make_disc("ENC-ESYS", "ENGENHARIA DE SISTEMAS", 6, 60, pre=["ENC-ES1"], ext=60, grupo="UFSCar ENC"),
        _make_disc("ENC-AAD", "ARQUITETURAS DE ALTO DESEMPENHO", 7, 60, pre=["ENC-AOC1"], grupo="UFSCar ENC"),
        _make_disc("ENC-SDIST", "SISTEMAS DISTRIBUÍDOS", 7, 60, pre=["ENC-SO"], ext=15, grupo="UFSCar ENC"),
        _make_disc("ENC-RC", "REDES DE COMPUTADORES", 7, 60, pre=["ENC-SO"], grupo="UFSCar ENC"),
        _make_disc("ENC-TC", "TECNOLOGIA DE COMUNICAÇÃO", 7, 60, pre=["ENC-SO"], grupo="UFSCar ENC"),
        _make_disc("ENC-PSCE", "PROJETO DE SISTEMAS COMPUTACIONAIS EMBARCADOS", 7, 60, pre=["ENC-AOC2", "ENC-ESYS"], ext=60, grupo="UFSCar ENC"),
        _make_disc("ENC-PPD", "PROGRAMAÇÃO PARALELA E DISTRIBUÍDA", 8, 60, pre=["ENC-SO"], grupo="UFSCar ENC"),
        _make_disc("ENC-IHC", "INTERAÇÃO HUMANO-COMPUTADOR", 8, 60, pre=["ENC-CAP"], grupo="UFSCar ENC"),
        _make_disc("ENC-OPT", "OTIMIZAÇÃO MATEMÁTICA", 8, 60, pre=["ENC-C2"], grupo="UFSCar ENC"),
        _make_disc("ENC-MC", "METODOLOGIA CIENTÍFICA", 8, 60, grupo="UFSCar ENC"),
        _make_disc("ENC-SEM2", "SEMINÁRIOS 2", 8, 30, pre=["ENC-SEM1"], ext=30, grupo="UFSCar ENC"),
        _make_disc("ENC-TCC1", "TRABALHO DE CONCLUSÃO DE CURSO 1", 9, 30, pre=["ENC-MC"], grupo="UFSCar ENC"),
        _make_disc("ENC-EST", "ESTÁGIO EM ENGENHARIA DE COMPUTAÇÃO", 10, 180, grupo="UFSCar ENC"),
        _make_disc("ENC-TCC2", "TRABALHO DE CONCLUSÃO DE CURSO 2", 10, 90, pre=["ENC-TCC1"], grupo="UFSCar ENC"),
    ]

    ia_pos_discs = [
        _make_disc("IA27-FMAT", "FUNDAMENTOS MATEMÁTICOS PARA IA (BACH. IA 2027)", 1, 60, grupo="UFSCar IA 2027"),
        _make_disc("IA27-ML", "APRENDIZADO DE MÁQUINA E REDES NEURAIS (BACH. IA 2027)", 2, 60, pre=["IA27-FMAT"], grupo="UFSCar IA 2027"),
        _make_disc("PPGCC-ES", "ENGENHARIA DE SOFTWARE AVANÇADA (PPGCC)", 1, 60, tipo="optativa", grupo="PPGCC Stricto Sensu"),
        _make_disc("PPGCC-VVTS", "VERIFICAÇÃO, VALIDAÇÃO E TESTE DE SOFTWARE (PPGCC)", 1, 60, tipo="optativa", grupo="PPGCC Stricto Sensu", topicos=["Qualidade", "Verificação e validação", "Critérios e ferramentas de teste", "TDD"]),
        _make_disc("PPGCC-AS", "ARQUITETURA DE SOFTWARE E SISTEMAS AUTÔNOMOS (PPGCC)", 2, 60, tipo="optativa", pre=["PPGCC-ES"], grupo="PPGCC Stricto Sensu"),
        _make_disc("PPGCC-SEGCIB", "SEGURANÇA DE SISTEMAS E REDES (PPGCC)", 2, 60, tipo="optativa", grupo="PPGCC Stricto Sensu", topicos=["Criptografia", "Auditoria", "Análise de riscos", "Testes de invasão"]),
        _make_disc("PPGCC-AM", "APRENDIZADO DE MÁQUINA (PPGCC)", 1, 60, tipo="optativa", grupo="PPGCC Stricto Sensu"),
        _make_disc("PPGCC-PLN", "PROCESSAMENTO DE LÍNGUAS NATURAIS (PPGCC)", 2, 60, tipo="optativa", pre=["PPGCC-AM"], grupo="PPGCC Stricto Sensu"),
        _make_disc("LATO-DEVOPS", "PRÁTICAS ÁGEIS, DEVOPS E TESTES AUTOMATIZADOS (ESP. 2027)", 1, 60, tipo="optativa", grupo="Lato Sensu DC-UFSCar"),
        _make_disc("LATO-ARQ", "ARQUITETURA DE SOFTWARE E MICROSSERVIÇOS (ESP. 2027)", 2, 60, tipo="optativa", pre=["LATO-DEVOPS"], grupo="Lato Sensu DC-UFSCar"),
        _make_disc("LATO-MOBILE", "DESENVOLVIMENTO WEB E MOBILE MULTIPLATAFORMA (ESP. 2027)", 2, 60, tipo="optativa", grupo="Lato Sensu DC-UFSCar"),
    ]

    specs = [
        ("ufscar_bcc", bcc_discs, 3240.0),
        ("ufscar_enc", enc_discs, 3660.0),
        ("ufscar_ia_pos", ia_pos_discs, 660.0),
    ]
    out: Dict[str, Curriculo] = {}
    for key, discs, total_ch in specs:
        meta = USP_COURSES[key]
        out[key] = Curriculo(
            curso=meta["curso"],
            campus=meta["campus"],
            vigencia="PPC UFSCar São Carlos (2025 / 2026–2027)",
            duracao_semestres=meta["duracao_semestres"],
            carga_horaria_total_curso=total_ch,
            disciplinas=discs,
            requisitos_gerais=_ppc_requisitos_for(key),
        )
    return out


def load_usp_curricula(processed_dir: Path) -> Dict[str, Curriculo]:
    path = processed_dir / USP_CURRICULA_FILE
    curricula: Dict[str, Curriculo] = {}
    if path.exists():
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
            curricula = {k: Curriculo.model_validate(v) for k, v in raw.items()}
        except Exception:
            curricula = {}

    for key, cur in curricula.items():
        if key in USP_COURSES and not any("Estrutura PPC" in r.item for r in cur.requisitos_gerais):
            cur.requisitos_gerais = _ppc_requisitos_for(key)

    # Mescla automaticamente os currículos oficiais da UFSCar São Carlos
    for u_key, u_cur in build_ufscar_curricula().items():
        curricula[u_key] = u_cur

    # Garante que disciplinas cursadas/em andamento pelo aluno especial apareçam apenas nos fluxogramas USP
    aluno = load_usp_aluno(processed_dir)
    extra_discs = (aluno or {}).get("disciplinas_aluno") or []
    if extra_discs:
        for k, cur in curricula.items():
            if USP_COURSES.get(k, {}).get("org", "usp") != "usp":
                continue
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
    """Busca (com cache em disco) a ementa oficial no JupiterWeb ou base local UFSCar."""
    code = sgldis.strip().upper()
    if code in UFSCAR_LOCAL_EMENTAS:
        return UFSCAR_LOCAL_EMENTAS[code]
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


_SYNONYMS = {
    "mobile": "movel",
    "moveis": "movel",
    "dispositivos": "movel",
    "celular": "movel",
    "celulares": "movel",
    "aplicacoes": "app",
    "aplicativos": "app",
    "desenvolvimento": "dev",
    "programacao": "dev",
    "inspecao": "teste",
    "testes": "teste",
    "verificacao": "teste",
    "validacao": "teste",
    "vv": "teste",
    "seguranca": "seg",
    "auditoria": "seg",
    "cibernetica": "seg",
    "criptografia": "seg",
    "arquitetura": "arq",
    "arquiteturas": "arq",
    "orientados": "oo",
    "orientada": "oo",
    "objetos": "oo",
    "objeto": "oo",
    "padroes": "padrao",
    "discreta": "matematica",
    "estruturas": "estrutura",
    "algoritmo": "algoritmos",
    "competitiva": "algoritmos",
    "redes": "rede",
    "banco": "bd",
    "bancos": "bd",
    "multiplataforma": "hibrido",
}

# Equivalências curadas e validadas diretamente pelas ementas oficiais (JupiterWeb USP e PPCs UFSCar)
_CURATED_EQUIVALENCES = {
    ("SCC0225", "SCLPRDM"): (95, "Alta", ["mobile", "dispositivos moveis", "interface", "aplicacoes nativas"]),
    ("SSC0961", "SCLPRDM"): (90, "Alta", ["computacao movel", "interface grafica", "persistencia", "hardware", "http webservice"]),
    ("UFSCAR-DMOV", "SCLPRDM"): (95, "Alta", ["computacao movel", "interface grafica", "persistencia", "http webservice"]),
    ("LATO-MOBILE", "SCLPRDM"): (92, "Alta", ["mobile", "persistencia", "webservices"]),
    ("SCC0225", "SCLDMDM"): (88, "Alta", ["dispositivos moveis", "arquitetura", "interface", "acessibilidade"]),
    ("UFSCAR-DMOV", "SCLDMDM"): (88, "Alta", ["aplicacoes nativas e multiplataforma", "persistencia", "webservices"]),
    ("LATO-MOBILE", "SCLDMDM"): (90, "Alta", ["web e mobile multiplataforma", "persistencia", "webservices"]),
    ("SSC0961", "SCLDMDM"): (75, "Alta", ["mobile", "frameworks multiplataforma", "webservices"]),
    ("SSC0524", "SCLVVTS"): (99, "Alta", ["verificacao", "validacao", "teste unidade integracao sistema regressao", "tdd"]),
    ("SSC0959", "SCLVVTS"): (96, "Alta", ["qualidade", "inspecao", "teste unidade integracao sistema regressao"]),
    ("UFSCAR-ES2", "SCLVVTS"): (85, "Alta", ["verificacao e validacao", "testes unidade integracao sistema", "tdd"]),
    ("PPGCC-VVTS", "SCLVVTS"): (99, "Alta", ["verificacao e validacao", "criterios e ferramentas de teste", "tdd"]),
    ("LATO-DEVOPS", "SCLVVTS"): (82, "Alta", ["testes automatizados", "ci/cd", "qualidade"]),
    ("SSC0547", "SCLASEG"): (88, "Alta", ["criptografia", "hash", "rsa", "autenticacao", "ids", "firewalls", "padroes seguranca"]),
    ("SSC0900", "SCLASEG"): (88, "Alta", ["ameacas", "hacking etico", "criptografia", "autenticacao", "controle acesso"]),
    ("SSC0901", "SCLASEG"): (82, "Alta", ["testes invasao", "portscan", "snort", "firewall", "exploracao falhas"]),
    ("UFSCAR-SEGCIB", "SCLASEG"): (92, "Alta", ["seguranca informacao", "criptografia pki", "auditoria", "testes invasao"]),
    ("PPGCC-SEGCIB", "SCLASEG"): (90, "Alta", ["auditoria", "criptografia", "analise riscos", "testes invasao"]),
    ("SSC0725", "SCLARSW"): (99, "Alta", ["arquitetura software", "estilos arquiteturais", "visoes", "avaliacao"]),
    ("UFSCAR-ASP", "SCLARSW"): (95, "Alta", ["estilos arquiteturais", "atributos qualidade", "avaliacao arquitetural"]),
    ("LATO-ARQ", "SCLARSW"): (95, "Alta", ["arquitetura software", "padroes", "microsservicos"]),
    ("PPGCC-AS", "SCLARSW"): (92, "Alta", ["arquitetura software", "estilos", "sistemas"]),
    ("SSC0158", "SCLARSW"): (78, "Alta", ["arquitetura orientada servicos", "nuvem", "sistemas distribuidos"]),
    ("SSC0124", "SCLAPOO"): (85, "Alta", ["uml", "casos uso", "sequencia", "padroes responsabilidade", "dependencia_apoo"]),
    ("UFSCAR-POOA", "SCLAPOO"): (84, "Alta", ["uml", "gof", "grasp solid", "persistencia"]),
    ("UFSCAR-ES1", "SCLAPOO"): (82, "Alta", ["uml", "casos uso", "analise projeto oo"]),
    ("SMA0805", "SCLMATC"): (99, "Alta", ["conjuntos", "relacoes", "funcoes"]),
    ("SMA0180", "SCLMATC"): (88, "Alta", ["combinatoria", "relacoes", "teoria numeros", "grafos"]),
    ("UFSCAR-MD", "SCLMATC"): (92, "Alta", ["logica formal", "inducao", "relacoes", "grafos"]),
    ("SSC0540", "SCLRCO2"): (99, "Alta", ["redes computadores", "servicos rede", "roteamento", "seguranca"]),
    ("SSC0142", "SCLRCO2"): (99, "Alta", ["redes computadores", "protocolos", "servicos rede"]),
    ("UFSCAR-RC", "SCLRCO2"): (90, "Alta", ["tcp ip", "infraestrutura", "servicos rede", "firewall"]),
    ("UFSCAR-PAA2", "SCLTAED"): (92, "Alta", ["programacao competitiva", "paradigmas algoritmos", "complexidade"]),
    ("UFSCAR-PAA", "SCLTAED"): (86, "Alta", ["projeto analise algoritmos", "complexidade", "grafos"]),
    ("UFSCAR-DEVOPS", "SCLTTEC"): (88, "Alta", ["ci cd", "automacao", "containers", "tecnologias emergentes"]),
    ("LATO-DEVOPS", "SCLTTEC"): (86, "Alta", ["praticas ageis", "devops", "testes automatizados"]),
}


def _sig_tokens(name: str, extra: Optional[List[str]] = None) -> set:
    raw = f"{name} {' '.join(extra or ())}"
    words = re.findall(r"[a-z0-9]{3,}", _norm(raw))
    out = set()
    for w in words:
        if w in _STOPWORDS:
            continue
        out.add(_SYNONYMS.get(w, w))
    return out


def _level_num(name: str) -> Optional[str]:
    m = re.search(r"\b(iii|ii|iv|i|1|2|3|4)\b", _norm(name))
    if not m:
        return None
    return {"i": "1", "ii": "2", "iii": "3", "iv": "4"}.get(m.group(1), m.group(1))


def compute_equivalences(ifsp: Curriculo, usp_map: Dict[str, Curriculo], curso_filter: str = "all") -> List[dict]:
    """Calcula equivalências candidatas entre USP/UFSCar São Carlos e IFSP BES (léxico + sinônimos + ementa)."""
    ifsp_by_code = {d.codigo: d for d in ifsp.disciplinas}
    best_by_pair: Dict[tuple, dict] = {}
    skip_ifsp = {"SCLING1", "SCLING2", "SCLCLIBR", "SCLAXB1", "SCLAXB2", "SCLAXB3", "SCLAXB4"}

    for usp_key, usp_cur in usp_map.items():
        if curso_filter != "all" and usp_key != curso_filter:
            continue
        course_label = USP_COURSES.get(usp_key, {}).get("label", usp_key)
        for u in usp_cur.disciplinas:
            u_toks = _sig_tokens(u.nome, u.topicos_principais[:4])
            u_lvl = _level_num(u.nome)
            for f in ifsp.disciplinas:
                if f.codigo in skip_ifsp:
                    continue
                curated = _CURATED_EQUIVALENCES.get((u.codigo, f.codigo))
                ch_ratio = (u.carga_horaria_total / f.carga_horaria_total) if f.carga_horaria_total else 1.0

                if curated:
                    pct, nivel, terms = curated
                else:
                    if not u_toks:
                        continue
                    f_toks = _sig_tokens(f.nome, f.topicos_principais[:4])
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

                    if score < 0.35:
                        continue
                    pct = min(99, round(score * 100))
                    if pct >= 70 and ch_ratio >= 0.75:
                        nivel = "Alta"
                    elif pct >= 45 and ch_ratio >= 0.5:
                        nivel = "Parcial"
                    else:
                        continue
                    terms = sorted(inter)

                key = (usp_key, u.codigo, f.codigo)
                prev = best_by_pair.get(key)
                if prev and prev["similaridade_pct"] >= pct:
                    continue
                target_f = ifsp_by_code.get(f.codigo, f)
                best_by_pair[key] = {
                    "usp_curso": usp_key,
                    "usp_curso_label": course_label,
                    "usp_codigo": u.codigo,
                    "usp_nome": u.nome,
                    "usp_ch": u.carga_horaria_total,
                    "ifsp_codigo": target_f.codigo,
                    "ifsp_nome": target_f.nome,
                    "ifsp_ch": target_f.carga_horaria_total,
                    "ifsp_semestre": target_f.semestre,
                    "ch_ratio": round(ch_ratio, 2),
                    "similaridade_pct": pct,
                    "equivalencia": nivel,
                    "termos_comuns": terms,
                }

    matches = list(best_by_pair.values())
    matches.sort(key=lambda m: (0 if m["equivalencia"] == "Alta" else 1, -m["similaridade_pct"], -m["ch_ratio"]))
    return matches


def _mermaid_id(code: str) -> str:
    return re.sub(r"[^A-Za-z0-9_]", "_", code.upper())


def _short_label(name: str, limit: int = 34) -> str:
    clean = name.replace('"', "'").replace("[", "(").replace("]", ")").strip()
    return clean if len(clean) <= limit else clean[: limit - 1].rstrip() + "…"


def build_course_mermaid(curriculo: Curriculo, course_key: str) -> str:
    """Converte o fluxograma completo de um curso em Mermaid compacto (economia máxima de tokens)."""
    by_sem: Dict[int, List[Disciplina]] = {}
    for d in sorted(curriculo.disciplinas, key=lambda x: (x.semestre or 99, x.codigo)):
        by_sem.setdefault(d.semestre or 99, []).append(d)

    valid = {d.codigo for d in curriculo.disciplinas}
    lines = ["```mermaid", "flowchart LR"]
    for sem in sorted(by_sem.keys()):
        sem_title = f"{sem}º Semestre" if sem < 99 else "Optativas / Livres"
        lines.append(f'  subgraph S{sem}_{_mermaid_id(course_key)}["{sem_title}"]')
        for d in by_sem[sem]:
            nid = _mermaid_id(d.codigo)
            opt_tag = " OPT" if d.tipo == "optativa" else (" ELE" if d.tipo == "eletiva" else "")
            ch = f"{d.carga_horaria_total:.0f}h"
            lines.append(f'    {nid}["{d.codigo}: {_short_label(d.nome)} ({ch}{opt_tag})"]')
        lines.append("  end")

    # Agrupa arestas por pré-requisito origem para compactar ainda mais tokens
    edges_by_pre: Dict[str, List[str]] = {}
    for d in sorted(curriculo.disciplinas, key=lambda x: (x.semestre or 99, x.codigo)):
        for pre in d.pre_requisitos:
            if pre in valid and pre != d.codigo:
                edges_by_pre.setdefault(_mermaid_id(pre), []).append(_mermaid_id(d.codigo))
    for pre_id, targets in edges_by_pre.items():
        lines.append(f"  {pre_id} --> {' & '.join(targets)}")
    lines.append("```")
    return "\n".join(lines)


def build_all_institutes_mermaid(ifsp_curriculo: Curriculo, external_curricula: Dict[str, Curriculo]) -> str:
    """Agrupa os fluxogramas Mermaid completos por instituto de ensino e inclui resumo dos PPCs."""
    institutes = [
        ("IFSP São Carlos", [("ifsp_bes", ifsp_curriculo, "PPC BES IFSP São Carlos (43 disciplinas, 3.207,2h, 8 semestres, integral).")]),
        (
            "USP São Carlos — ICMC / CAASO",
            [
                (k, external_curricula[k], USP_COURSES[k]["ppc_resumo"])
                for k in ("usp_bsi", "usp_bci", "usp_est")
                if k in external_curricula
            ],
        ),
        (
            "UFSCar São Carlos — DC / CCET & PPGCC",
            [
                (k, external_curricula[k], USP_COURSES[k]["ppc_resumo"])
                for k in ("ufscar_bcc", "ufscar_enc", "ufscar_ia_pos")
                if k in external_curricula
            ],
        ),
    ]
    sections = []
    for inst_name, items in institutes:
        if not items:
            continue
        sections.append(f"## Instituto: {inst_name}")
        for key, cur, resumo in items:
            meta = USP_COURSES.get(key, {})
            sections.append(
                f"### {cur.curso} [`{key}`]\n"
                f"- Disciplinas mapeadas: {len(cur.disciplinas)} · Duração: {cur.duracao_semestres} semestres\n"
                f"- PPC: {resumo}" + (f"\n- Link PPC: {meta['ppc_url']}" if meta.get("ppc_url") else "") + "\n"
                + build_course_mermaid(cur, key)
            )
    return "\n\n".join(sections)


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
