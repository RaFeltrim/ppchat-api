"""Suíte completa de QA (Unitários, Integração, Smoke, E2E, Carga e Performance) — PPChat."""

import json
import sys
import time
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from unittest.mock import patch

import fitz
from fastapi.testclient import TestClient

from src.modules.api.app import app
from src.modules.api.rate_limit import RateLimiter
from src.modules.api.moodle_import import MoodleTask, format_moodle_summary
from src.modules.api.suap_import import ImportStore
from src.modules.ingestion.models.curriculum import Curriculo, Disciplina
from src.modules.knowledge.services.curriculum_graph import CurriculumGraph
from src.modules.knowledge.services.ifsp_drive import search_ifsp_docs
from src.modules.knowledge.services.knowledge_base import get_knowledge_base
from src.modules.knowledge.services.usp_jupiter import build_suap_requerimento, compute_equivalences
from src.modules.response.services.chat_service import ChatSession
from src.modules.response.services.model_router import route_inference
from src.modules.shared.services.settings import get_settings


def _fake_pdf_bytes(text: str = "Ementa teste Engenharia de Software") -> bytes:
    doc = fitz.open()
    page = doc.new_page()
    page.insert_text((72, 72), text)
    data = doc.tobytes()
    doc.close()
    return data


class _FakeUsage:
    input_tokens = 120
    cache_read_input_tokens = 80
    cache_creation_input_tokens = 0
    output_tokens = 45


class _FakeMessage:
    model = "deepseek/deepseek-v4.1-flash"
    usage = _FakeUsage()
    content = [type("Block", (), {"type": "text", "text": "Resposta simulada com [Página 48]."})()]


class _FakeDelta:
    def __init__(self, dtype: str, val: str):
        self.type = dtype
        if dtype == "thinking_delta":
            self.thinking = val
        else:
            self.text = val


class _FakeEvent:
    def __init__(self, dtype: str, val: str):
        self.type = "content_block_delta"
        self.delta = _FakeDelta(dtype, val)


class _FakeStreamCtx:
    def __await__(self):
        async def _ret():
            return self
        return _ret().__await__()

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        return False

    def __aiter__(self):
        self._events = iter([
            _FakeEvent("thinking_delta", "Analisando PPC..."),
            _FakeEvent("text_delta", "Resposta simulada com [Página 48]."),
        ])
        return self

    async def __anext__(self):
        try:
            return next(self._events)
        except StopIteration:
            raise StopAsyncIteration

    async def get_final_message(self):
        return _FakeMessage()


class _FakeBetaMessages:
    def stream(self, **kwargs):
        return _FakeStreamCtx()


class _FakeBeta:
    def __init__(self):
        self.messages = _FakeBetaMessages()


class _FakeAsyncClient:
    def __init__(self):
        self.beta = _FakeBeta()


class TestUnitComponents(unittest.TestCase):
    def test_curriculum_graph_analysis(self):
        d1 = Disciplina(codigo="D1", nome="Intro", semestre=1, tipo="obrigatoria", aulas_semanais=4, total_aulas=60, carga_horaria_ensino=50, carga_horaria_extensao=0, carga_horaria_total=50, abordagem="teorica", usa_laboratorio=False, pre_requisitos=[], grupos_conhecimento=["GC"], topicos_principais=["T1"], pagina_plano_ensino=10)
        d2 = Disciplina(codigo="D2", nome="Avancado", semestre=2, tipo="obrigatoria", aulas_semanais=4, total_aulas=60, carga_horaria_ensino=50, carga_horaria_extensao=0, carga_horaria_total=50, abordagem="pratica", usa_laboratorio=True, pre_requisitos=["D1"], grupos_conhecimento=["GC"], topicos_principais=["T2"], pagina_plano_ensino=12)
        cur = Curriculo(curso="BES", campus="SCL", vigencia="2023", duracao_semestres=8, carga_horaria_total_curso=100, disciplinas=[d1, d2], requisitos_gerais=[])
        g = CurriculumGraph(cur)
        self.assertEqual(g.critical_path, ["D1", "D2"])
        self.assertEqual(g.analysis["D1"].libera_transitivamente, ["D2"])
        self.assertEqual(g.analysis["D2"].profundidade, 1)

    def test_llm_client_and_knowledge_base_renderers(self):
        from src.modules.shared.services.llm_client import get_llm_client, get_async_llm_client
        self.assertIsNotNone(get_llm_client())
        self.assertIsNotNone(get_async_llm_client())
        kb = get_knowledge_base()
        txt = kb.render_disciplinas(["SCLAPOO", "SSC0124"])
        self.assertIn("SCLAPOO", txt)
        self.assertIn("SSC0124", txt)
        docs_txt = kb.render_ifsp_docs("aproveitamento exape")
        self.assertIn("Link oficial", docs_txt)

    def test_slm_first_router_matrix(self):
        s = get_settings()
        d_faq = route_inference("Qual a carga horaria de Redes?", requested_model="auto", settings=s)
        self.assertEqual(d_faq.tier, "slm")
        self.assertEqual(d_faq.effort, "low")

        d_eq = route_inference("Quais disciplinas devo puxar como aluno especial na USP?", requested_model="auto", settings=s)
        self.assertEqual(d_eq.tier, "llm")

        d_doc = route_inference("Resuma", has_docs=True, requested_model="auto", settings=s)
        self.assertEqual(d_doc.tier, "llm")

        d_hist = route_inference("Oi", history_len=4, requested_model="auto", settings=s)
        self.assertEqual(d_hist.tier, "llm")

        d_manual = route_inference("Oi", requested_model="google/gemini-3.8-flash", settings=s)
        self.assertEqual(d_manual.tier, "manual")
        self.assertEqual(d_manual.model, "google/gemini-3.8-flash")

    def test_ifsp_drive_search_and_rate_limiter(self):
        kb = get_knowledge_base()
        hits = search_ifsp_docs(kb.ifsp_docs, "preciso fazer exape e aproveitamento", limit=3)
        self.assertGreaterEqual(len(hits), 1)

        rl = RateLimiter(per_ip=2, global_limit=10)
        self.assertIsNone(rl.check("10.0.0.1"))
        self.assertIsNone(rl.check("10.0.0.1"))
        self.assertIsNotNone(rl.check("10.0.0.1"))

    def test_moodle_summary_and_import_store(self):
        txt = format_moodle_summary([MoodleTask(title="Entrega 1", course="APOO", due="Hoje", url="https://moodle.scl.ifsp.edu.br/1")])
        self.assertIn("Entrega 1", txt)
        store = ImportStore()
        code = store.put({"ok": True})
        self.assertEqual(store.take(code), {"ok": True})
        self.assertIsNone(store.take(code))

    def test_compute_equivalences_and_requerimento(self):
        kb = get_knowledge_base()
        eqs = compute_equivalences(kb.curriculo, kb.usp_curricula, curso_filter="usp_bsi")
        self.assertGreater(len(eqs), 0)
        self.assertEqual(eqs[0]["equivalencia"], "Alta")
        ifsp_d = kb.graph.by_code["SCLARCO"]
        usp_d = kb.usp_graphs["usp_bsi"].by_code["SSC0513"]
        req = build_suap_requerimento(ifsp_d, usp_d, {"programa_resumido": "Arquitetura", "url": "https://uspdigital.usp.br"}, "USP · BSI", "Aluno", "SC123")
        self.assertTrue(req["atende_ch_75"])
        self.assertIn("REQUERIMENTO DE APROVEITAMENTO", req["minuta_markdown"])


class TestSmokeAndIntegrationAPI(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.client_cm = TestClient(app)
        cls.client = cls.client_cm.__enter__()

    @classmethod
    def tearDownClass(cls):
        cls.client_cm.__exit__(None, None, None)

    def test_smoke_ui_and_static_assets(self):
        r = self.client.get("/")
        self.assertEqual(r.status_code, 200)
        for marker in ("org-select", "inst-select", "model-select", 'value="auto"', "add-document", "moodle-btn", "suap-btn"):
            self.assertIn(marker, r.text)
        for asset in ("/static/app.js", "/static/styles.css", "/static/moodle-export.js", "/static/suap-export.js", "/pdf"):
            ra = self.client.get(asset)
            self.assertEqual(ra.status_code, 200, asset)

    def test_health_curriculum_and_ifsp_docs(self):
        rh = self.client.get("/health")
        self.assertEqual(rh.status_code, 200)
        self.assertEqual(rh.json()["disciplinas"], 43)

        for inst, min_count in (("ifsp_bes", 43), ("usp_bsi", 80), ("usp_bci", 130), ("usp_est", 70)):
            rc = self.client.get(f"/curriculum?inst={inst}")
            self.assertEqual(rc.status_code, 200)
            self.assertGreaterEqual(len(rc.json()["disciplinas"]), min_count)

        r_fb = self.client.get("/curriculum?inst=invalido")
        self.assertEqual(r_fb.status_code, 200)
        self.assertEqual(r_fb.json()["inst"], "ifsp_bes")

        rd = self.client.get("/ifsp-docs")
        self.assertEqual(rd.status_code, 200)
        self.assertEqual(rd.json()["count"], 20)

    def test_documents_extract_validation_and_pdf(self):
        r_pdf = self.client.post("/documents/extract", files={"file": ("ementa.pdf", _fake_pdf_bytes("Conteudo PDF Teste"), "application/pdf")})
        self.assertEqual(r_pdf.status_code, 200)
        self.assertIn("Conteudo PDF Teste", r_pdf.json()["content"])

        r_big = self.client.post("/documents/extract", files={"file": ("grande.txt", b"A" * 45000, "text/plain")})
        self.assertEqual(r_big.status_code, 200)
        self.assertTrue(r_big.json()["truncated"])
        self.assertEqual(len(r_big.json()["content"]), 40000)

        r_bad = self.client.post("/documents/extract", files={"file": ("malware.exe", b"MZ", "application/octet-stream")})
        self.assertEqual(r_bad.status_code, 400)

    def test_moodle_suap_and_path_traversal_security(self):
        rm = self.client.post("/moodle/importar", json={"tasks": [{"title": "T1", "course": "APOO", "due": "", "url": ""}], "notify_whatsapp": False})
        self.assertEqual(rm.status_code, 200)
        tok = rm.json()["token"]
        self.assertEqual(self.client.get(f"/moodle/resgatar/{tok}").status_code, 200)
        self.assertEqual(self.client.get(f"/moodle/resgatar/{tok}").status_code, 404)

        # Path traversal bloqueado
        rt = self.client.get("/moodle/file", params={"folder": "..", "path": ".env"})
        self.assertEqual(rt.status_code, 404)

        # SUAP import + local state + moodle repos + cancel
        suap_payload = {"versao": 2, "matricula": "SC0001", "coletado_em": "2026-11-18T00:00:00Z", "abas": [{"titulo": "Histórico", "tabelas": []}]}
        rs = self.client.post("/aluno/importar", json=suap_payload)
        self.assertEqual(rs.status_code, 200)
        sc = rs.json()["code"]
        self.assertEqual(self.client.get(f"/aluno/importar/{sc}").status_code, 200)
        self.assertEqual(self.client.get(f"/aluno/importar/{sc}").status_code, 404)
        self.assertEqual(self.client.get("/local/state").status_code, 200)
        self.assertEqual(self.client.get("/moodle/repos").status_code, 200)
        self.assertEqual(self.client.post("/chat/cancel/no-such-id").status_code, 204)

    def test_usp_endpoints_and_requerimento(self):
        re_list = self.client.get("/usp/equivalencias?curso=usp_bsi")
        self.assertEqual(re_list.status_code, 200)
        self.assertGreater(re_list.json()["count"], 0)

        r_disc = self.client.get("/usp/disciplina/SSC0124")
        self.assertEqual(r_disc.status_code, 200)
        self.assertGreater(len(r_disc.json().get("programa", "")), 50)

        r_req = self.client.post("/usp/requerimento", json={"ifsp_codigo": "SCLARCO", "usp_codigo": "SSC0513", "aluno_nome": "QA", "matricula": "SC001"})
        self.assertEqual(r_req.status_code, 200)
        self.assertTrue(r_req.json()["atende_ch_75"])

        self.assertEqual(self.client.post("/usp/requerimento", json={"ifsp_codigo": "INEXISTENTE", "usp_codigo": "SSC0513"}).status_code, 404)


class TestE2EChatWorkflow(unittest.TestCase):
    def test_e2e_multi_institution_chat_stream_and_doc_attach(self):
        with patch("src.modules.response.services.chat_service.get_async_llm_client", return_value=_FakeAsyncClient()):
            with TestClient(app) as client:
                # 1. Upload ementa PDF
                up = client.post("/documents/extract", files={"file": ("plano.pdf", _fake_pdf_bytes("Plano OO"), "application/pdf")})
                self.assertEqual(up.status_code, 200)
                doc_payload = {"name": up.json()["name"], "content": up.json()["content"]}

                # 2. Consulta stream com auto SLM-First + contexto unificado + documento + inst usp_bsi
                res = client.post(
                    "/chat/stream",
                    json={
                        "question": "Compare esta ementa com SSC0124 e SCLAPOO para equivalencia.",
                        "disciplinas": ["SCLAPOO", "SSC0124"],
                        "documentos": [doc_payload],
                        "perfil": "[IFSP · SUAP] Pendente SCLAPOO",
                        "inst": "usp_bsi",
                        "model": "auto",
                        "request_id": "e2e-req-1",
                    },
                )
                self.assertEqual(res.status_code, 200)
                events = [json.loads(ln) for ln in res.text.strip().splitlines() if ln.strip()]
                types = [e["type"] for e in events]
                self.assertIn("thinking", types)
                self.assertIn("text", types)
                self.assertEqual(types[-1], "done")
                self.assertEqual(events[-1]["usage"]["model"], "deepseek/deepseek-v4.1-flash")

                # 3. Consulta sincrona /chat
                res_sync = client.post("/chat", json={"question": "Qual a carga horaria total do curso?", "model": "auto"})
                self.assertEqual(res_sync.status_code, 200)
                self.assertIn("answer", res_sync.json())


class TestLoadAndPerformanceSLA(unittest.TestCase):
    def test_concurrent_load_40_requests_and_latency_sla(self):
        with TestClient(app) as client:
            endpoints = ["/health", "/curriculum?inst=ifsp_bes", "/ifsp-docs", "/usp/equivalencias"]

            def _hit(idx: int):
                t0 = time.perf_counter()
                r = client.get(endpoints[idx % len(endpoints)])
                return r.status_code, (time.perf_counter() - t0) * 1000.0

            with ThreadPoolExecutor(max_workers=8) as pool:
                results = list(pool.map(_hit, range(40)))

            statuses = [s for s, _ in results]
            latencies = sorted(ms for _, ms in results)
            self.assertTrue(all(s == 200 for s in statuses), statuses)
            p95 = latencies[int(0.95 * len(latencies)) - 1]
            sla_ms = 1200.0 if sys.gettrace() else 250.0
            self.assertLess(p95, sla_ms, f"p95 latency too high: {p95:.1f}ms (SLA < {sla_ms}ms)")


if __name__ == "__main__":
    unittest.main(verbosity=2)
