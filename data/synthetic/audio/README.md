# Áudios sintéticos (gerados — não versionados)

> 🇧🇷 Você está lendo este README em português. **[Read this document in English](README.en.md).**

**Este diretório é gerado e os `.wav`/`.mp3` são ignorados pelo git** (13 MB de
binários reproduzíveis — mesma política do `metrics.jsonl`). Numa cópia limpa do
repositório o diretório nem aparece até que você gere os áudios.

Os 12 arquivos vêm das transcrições em [`../transcripts/`](../transcripts)
(versionadas) lidas por uma voz de TTS — ou seja, áudio **100% sintético**:
um sintetizador lendo textos fictícios. Nenhum paciente real está envolvido.

## Como gerar

```bash
uv sync --extra tts                            # instala o piper-tts
uv run python scripts/make_synthetic_audio.py  # gera os 12 WAVs aqui
```

Opções úteis:

```bash
uv run python scripts/make_synthetic_audio.py --limit 2        # só os dois primeiros
uv run python scripts/make_synthetic_audio.py --slug endodontia # só um caso
uv run python scripts/make_synthetic_audio.py --engine espeak-ng # sem piper (apt install espeak-ng)
```

- **piper** (padrão): baixa a voz `pt_BR-faber-medium` uma vez para
  `~/.cache/piper` — a única etapa que precisa de rede, como o download do
  modelo Whisper.
- **espeak-ng**: usado automaticamente se o binário estiver no PATH, sem
  dependência Python.

Depois, a demo ponta a ponta:

```bash
uv run dentanote run data/synthetic/audio/restauracao_classe_I.wav
```

## Regras

- **Não commite WAV/MP3** — as regras no `.gitignore` (`data/synthetic/audio/*.wav`
  e `*.mp3`) são propositais; o texto-fonte é a transcrição.
- O que os áudios carregam é coberto pelas regras do corpus em
  [`../README.md`](../README.md): só informação que aparece literalmente na
  transcrição, nada inferido, nada real.
