# Backlog ágil — DentaNote

Metodologia: **sprints curtos = fases do `PROMPT.md`**. Cada fase é um incremento
entregável, com critério de aceite verificável, testes automatizados e **um commit ao
final** (Conventional Commits). Nada de trabalho "solto": se a fase não passa em
`ruff + mypy + pytest`, ela não está pronta.

## Quadro

| Sprint | Fase | Histórias | Critério de aceite | Status |
| --- | --- | --- | --- | --- |
| S0 | Fundação | Repo git, licença MIT, tooling, backlog | `uv sync` roda; repo versionado | ✅ |
| S1 | Fase 1 | Esqueleto, `pyproject.toml`, `config.py`, `schema.py` + testes | `pytest` verde cobrindo FDI/schema/config | ⏳ |
| S2 | Fase 2 | `transcribe.py`, `extract.py`, `prompts.py`, CLI com texto | JSON válido em ≥90% das transcrições sintéticas com Ollama real | pendente |
| S3 | Fase 3 | `render.py` determinístico, `pipeline.py`, `metrics.py` | Texto final não inventa campo ausente; `metrics.jsonl` sem PHI (teste) | pendente |
| S4 | Fase 4 | 12+ transcrições sintéticas, `evaluate.py`, comparação de modelos | `docs/results.md` gerado com precisão/recall/F1 e tabela de modelos | pendente |
| S5 | Fase 5 | Interface Streamlit + `dentanote doctor` | Demo em 1 clique, aviso de rascunho fixo, status offline | pendente |
| S6 | Fase 6 | CI (GitHub Actions), README, docs, diagrama | CI verde: ruff + mypy + pytest em 3.11/3.12 | pendente |
| S7 | Fase 7 | `docs/post_draft.md` | Post em PT-BR com tags e marcadores `[INSERIR: ...]` | pendente |

## Definição de pronto (DoD)

1. Código e comentários em inglês; textos de UI/README em PT-BR.
2. `ruff check .`, `ruff format --check .`, `mypy src` e `pytest` verdes antes do commit.
3. Nenhum dado real de paciente; logs/métricas só com tempos, contagens e tamanhos.
4. Saída do sistema sempre rotulada como rascunho revisável.
5. Commit Conventional Commits pequeno, com o "porquê" no corpo.

## Decisões de design registradas (ADR curtos)

- **ADR-001 — Saída estruturada via `format` (JSON Schema) do Ollama.** Constrained
  decoding zera a probabilidade de tokens fora do schema; ainda assim o cliente valida
  com Pydantic porque modelos "thinking" podem ignorar o schema (ver
  <https://dev.to/homelabpm/ollama-skips-your-json-schema-when-a-thinking-model-answers-without-thinking-2916>).
  Por isso `think=false` por padrão e validação sempre no cliente.
- **ADR-002 — Renderização por template determinístico, nunca por LLM.** A última etapa
  não pode alucinar: ela só transcreve campos já validados (seção 5.4 do PROMPT).
- **ADR-003 — `uncertain_items` obrigatório como válvula de segurança.** Ambiguidade
  (dente falado de formas diferentes, número inválido) vira item listado para o
  profissional conferir, nunca é resolvido silenciosamente.
- **ADR-004 — Reparo limitado a 2 tentativas.** Erro de validação é reenviado ao modelo;
  se persistir, resultado parcial com aviso claro, sem exceção crua ao usuário.
- **ADR-005 — Modelo padrão do Ollama.** `ollama list` local lista `gemma4:e4b`
  (mais recente) e `gemma3:4b`; padrão = `gemma4:e4b`, alternativa documentada no README.
- **ADR-006 — Sem PHI em logs.** `metrics.jsonl` guarda apenas durações, contagens,
  tamanhos, modelo e nº de tentativas; há teste automatizado garantindo isso.
