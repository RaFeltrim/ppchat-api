# Arquitetura SLM-First (FinOps) & Referência `karpathy/nanochat` no PPChat

Este documento adapta os fundamentos de **Small Language Models (SLMs)** vs. **Large Language Models (LLMs)** e o pipeline didático **`karpathy/nanochat`** para a arquitetura do `ppchat-api`.

---

## 1. Roteamento Híbrido `SLM-First` no `ppchat-api`

Em vez de enviar todas as requisições para modelos generalistas pesados com raciocínio elevado, o `ppchat-api` combina três camadas complementares:

| Camada | Papel no `ppchat-api` | Onde atua |
| :--- | :--- | :--- |
| **Camada Determinística (0 tokens)** | Cálculos exatos sem chamada de API: grafo de pré-requisitos, gargalos, equivalências IFSP × USP, busca de formulários do Drive IFSP e geração da minuta SUAP. | `CurriculumGraph`, `usp_jupiter.py`, `ifsp_drive.py` |
| **Tier 0 · SLM Especialista (`SLM_MODEL` / `effort="low"`)** | Perguntas diretas e objetivas (ementa única, pré-requisito pontual, FAQ de formulário DDGA/SUAP, consultas curtas sem documentos anexados). | `route_inference()` em `model_router.py` |
| **Tier High · LLM Generalista (`LLM_MODEL` / `CHAT_EFFORT`)** | Planejamento semestre a semestre, análise de equivalências multi-institucionais (IFSP + USP + UFSCar), comparação com documentos anexados (`.pdf`/`.txt`) e conversas multi-turno longas (`>= 4` turnos). | `ChatSession` + Prompt Cache 1h |

### Configuração FinOps no `.env`
- `SLM_FIRST_ENABLED=true`: ativa o modo **Auto (SLM-First FinOps)** (`#model-select` = `auto`).
- `SLM_MODEL="qwen/qwen3.8-27b"`: modelo leve padrão para o Tier 0.
- `SLM_BASE_URL=""`: opcional para apontar inferência local compatível (ex.: LM Studio `:1234` ou Ollama `:11434`).
- Se o usuário selecionar manualmente qualquer modelo específico no `#model-select`, o roteador respeita a escolha (`tier="manual"`).

---

## 2. Os 5 Estágios do `karpathy/nanochat` Aplicados ao Domínio Acadêmico

O repositório [`karpathy/nanochat`](https://github.com/karpathy/nanochat) (licença MIT) demonstra ponta a ponta como um LLM/SLM moderno é construído e serve como laboratório de estudo para Engenharia de Software (IFSP / USP):

1. **Train the Tokenizer (BPE):** vocabulário ajustado a siglas acadêmicas (`SCL*`, `SSC*`, termos de PPC, código Python/JS) reduz o consumo de tokens por mensagem.
2. **Pretrain the Base Model:** aprendizado da estrutura de linguagem sobre grandes corpora.
3. **Fine-tune to Chat (SFT):** transformação em assistente instruído para responder perguntas acadêmicas estruturadas com citações `[Página N]`.
4. **Reinforcement Learning (RL / DPO):** alinhamento com pares de preferência (*Chosen vs. Rejected*) — aplicável futuramente para destilar um SLM especialista em ementas, geração de requerimentos SUAP e validação de equivalências.
5. **Talk to it (Inference & Web UI):** servidor de inferência com KV-Cache — conceito diretamente refletido no **Prompt Caching de 1h** usado em `ChatSession`.
