# Contribuindo com o DentaNote

Obrigado por querer contribuir! O projeto é pequeno de propósito e convida
contribuições de três tipos: **outras especialidades odontológicas** (mais
cenários sintéticos), **outros idiomas** (prompt, transcrição e renderização em
ES/EN) e **melhorias de engenharia** (desempenho, TTS, acessibilidade).

## Setup

```bash
git clone <repo>
cd anotadordental
uv sync --extra dev          # Python 3.11+; deps fixadas no pyproject
ollama pull gemma4:e4b       # modelo local (uma vez)
uv run dentanote doctor      # diagnostica o ambiente
```

Sem `uv`? `python -m venv .venv && pip install -e ".[dev]"` também funciona.

## Antes de abrir o PR

```bash
uv run ruff format .
uv run ruff check .
uv run mypy src scripts
uv run pytest -q -m "not slow"   # offline: sockets bloqueados, sem modelo real
```

O CI (GitHub Actions) roda exatamente isso em Python 3.11 e 3.12. Opcional,
localmente com Ollama ativo: `uv run pytest -q -m slow`.

## Regras que não se negociam

1. **Nenhum dado real de paciente** em código, teste, exemplo, print ou commit.
   Veja [SECURITY.md](SECURITY.md).
2. **Nenhuma chamada de rede em tempo de execução** além de
   `localhost:11434` (Ollama). Se o seu recurso precisar de internet, ele vem
   desativado por padrão e documentado.
3. **Saída é sempre rascunho**: nada de "diagnóstico" ou texto preenchido por
   inferência — lacuna vira `null`/lista vazia/`uncertain_items`.
4. **Sem PHI em logs/métricas**: só tempos, contagens e tamanhos (já há teste
   automatizado garantindo isso — não quebre o guard).

## Estilo

- Commits [Conventional Commits](https://www.conventionalcommits.org/)
  (`feat:`, `fix:`, `docs:`, `test:`, `chore:`).
- Código e comentários em **inglês**; textos de UI, README e exemplos
  clínicos em **português do Brasil**.
- `ruff` formata/linta, `mypy` checa tipos — sem suppressions novas sem
  justificativa.
- Cada PR com teste do comportamento novo ou alterado.

## Ideias boas para começar

- Transcrições sintéticas de outras especialidades (implantodontia,
  periodontia, ortodontia) com o `expected/` correspondente — o
  `scripts/evaluate.py` já mede o impacto.
- Vozes TTS/idiomas extras em `scripts/make_synthetic_audio.py`.
- Acessibilidade da interface (contraste, navegação por teclado, leitores de tela).
- Acompanhar `docs/post_draft.md` e o roadmap no README.
