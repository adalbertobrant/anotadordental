# Synthetic audio (generated — not versioned)

> 🇧🇷 [Versão em português](README.md).

**This directory is generated and the `.wav`/`.mp3` files are gitignored**
(13 MB of reproducible binaries — same policy as `metrics.jsonl`). In a clean
clone of the repository the directory doesn't even exist until you generate
the audio.

The 12 files come from the versioned transcripts in
[`../transcripts/`](../transcripts) read aloud by a TTS voice — that is,
**100% synthetic** audio: a synthesizer reading fictional texts. No real
patient is involved anywhere.

## How to generate

```bash
uv sync --extra tts                            # installs piper-tts
uv run python scripts/make_synthetic_audio.py  # writes the 12 WAVs here
```

Useful options:

```bash
uv run python scripts/make_synthetic_audio.py --limit 2         # only the first two
uv run python scripts/make_synthetic_audio.py --slug endodontia # only one case
uv run python scripts/make_synthetic_audio.py --engine espeak-ng # no piper (apt install espeak-ng)
```

- **piper** (default): downloads the `pt_BR-faber-medium` voice once into
  `~/.cache/piper` — the only step that needs the network, just like the
  Whisper model download.
- **espeak-ng**: used automatically when the binary is on PATH, with no
  Python dependency.

Then, the end-to-end demo:

```bash
uv run dentanote run data/synthetic/audio/restauracao_classe_I.wav
```

## Rules

- **Never commit WAV/MP3** — the `.gitignore` rules
  (`data/synthetic/audio/*.wav` and `*.mp3`) are deliberate; the source of
  truth is the transcript text.
- What the audio carries is covered by the corpus rules in
  [`../README.md`](../README.md): only information that literally appears in
  the transcript, nothing inferred, nothing real.
