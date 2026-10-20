#!/usr/bin/env python3
"""Render the synthetic transcripts to WAV with an offline TTS.

The output is **100% synthetic audio** (a TTS voice reading fictional
transcripts) — there is no real patient anywhere in this repository. The WAV
files land in ``data/synthetic/audio/`` (gitignored) and feed the end-to-end
demo: ``dentanote run data/synthetic/audio/<slug>.wav``.

Engines, in order of preference:

* ``piper`` (default): install with ``uv sync --extra tts`` (or
  ``pip install piper-tts==1.8.0``). The ``pt_BR-faber-medium`` voice is
  downloaded once to ``~/.cache/piper`` on first use — the single step that
  needs network, exactly like the Whisper model download.
* ``espeak-ng``: used automatically when the binary is on PATH (no Python
  dependency), e.g. ``apt install espeak-ng``.

Examples:

    uv run python scripts/make_synthetic_audio.py                # every transcript
    uv run python scripts/make_synthetic_audio.py --limit 2      # first two
    uv run python scripts/make_synthetic_audio.py --slug endodontia
    uv run python scripts/make_synthetic_audio.py --engine espeak-ng
"""

from __future__ import annotations

import argparse
import shutil
import subprocess
import wave
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TRANSCRIPTS_DIR = ROOT / "data" / "synthetic" / "transcripts"
OUT_DIR = ROOT / "data" / "synthetic" / "audio"

DEFAULT_VOICE = "pt_BR-faber-medium"
# Where piper keeps downloaded voices (override with --voice-dir).
DEFAULT_VOICE_DIR = Path.home() / ".cache" / "piper"

SYNTHETIC_NOTICE = (
    "ATENÇÃO: os WAV gerados são 100% sintéticos (TTS lendo transcrições "
    "fictícias). Nenhum paciente real está envolvido."
)


def synth_with_piper(text: str, out_path: Path, voice_name: str, voice_dir: Path) -> None:
    try:
        from piper import PiperVoice  # type: ignore[import-not-found]
        from piper.download_voices import download_voice
    except ImportError as exc:  # pragma: no cover - depends on optional extra
        raise SystemExit(
            "piper não está instalado. Rode `uv sync --extra tts` ou "
            "`pip install piper-tts==1.8.0` (ou use --engine espeak-ng)."
        ) from exc

    model_path = voice_dir / f"{voice_name}.onnx"
    config_path = voice_dir / f"{voice_name}.onnx.json"
    if not (model_path.exists() and config_path.exists()):
        print(f"Baixando a voz sintética {voice_name} (única etapa que precisa de rede)...")
        download_voice(voice_name, voice_dir)

    voice = PiperVoice.load(model_path, config_path)
    with wave.open(str(out_path), "wb") as wav_file:
        voice.synthesize_wav(text, wav_file)


def synth_with_espeak(text: str, out_path: Path) -> None:
    binary = shutil.which("espeak-ng") or shutil.which("espeak")
    if binary is None:
        raise SystemExit(
            "espeak-ng não encontrado no PATH. Instale com `apt install espeak-ng` "
            "ou use o engine piper (`uv sync --extra tts`)."
        )
    # Text goes through argv (never a shell): transcripts are fictional, but we
    # do not build shell strings from file contents either.
    subprocess.run(
        [binary, "-v", "pt-br", "-s", "160", "-w", str(out_path), text],
        check=True,
        capture_output=True,
    )


def main() -> None:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument(
        "--slug", action="append", default=None, help="Render only this slug (repeatable)."
    )
    parser.add_argument(
        "--limit", type=int, default=None, help="Render only the first N transcripts."
    )
    parser.add_argument(
        "--out-dir", type=Path, default=OUT_DIR, help="Where WAV files are written."
    )
    parser.add_argument(
        "--voice", default=DEFAULT_VOICE, help=f"piper voice (default: {DEFAULT_VOICE})."
    )
    parser.add_argument(
        "--voice-dir",
        type=Path,
        default=DEFAULT_VOICE_DIR,
        help="piper voice cache (default: ~/.cache/piper).",
    )
    parser.add_argument(
        "--engine",
        choices=("auto", "piper", "espeak-ng"),
        default="auto",
        help="TTS engine (default: auto = piper if installed, else espeak-ng).",
    )
    args = parser.parse_args()

    transcripts = sorted(TRANSCRIPTS_DIR.glob("*.txt"))
    if args.slug:
        wanted = set(args.slug)
        transcripts = [path for path in transcripts if path.stem in wanted]
        missing = wanted - {path.stem for path in transcripts}
        if missing:
            raise SystemExit(f"transcrições não encontradas: {', '.join(sorted(missing))}")
    if args.limit:
        transcripts = transcripts[: args.limit]
    if not transcripts:
        raise SystemExit(f"nenhuma transcrição em {TRANSCRIPTS_DIR}")

    engine = args.engine
    if engine == "auto":
        try:
            import piper  # noqa: F401

            engine = "piper"
        except ImportError:
            engine = "espeak-ng"

    args.out_dir.mkdir(parents=True, exist_ok=True)
    print(SYNTHETIC_NOTICE)
    print(f"Engine: {engine} · {len(transcripts)} transcrição(ões) -> {args.out_dir}\n")

    for path in transcripts:
        text = path.read_text(encoding="utf-8").strip()
        out_path = args.out_dir / f"{path.stem}.wav"
        if engine == "piper":
            synth_with_piper(text, out_path, args.voice, args.voice_dir)
        else:
            synth_with_espeak(text, out_path)
        with wave.open(str(out_path), "rb") as wav_file:
            frames = wav_file.getnframes()
            rate = wav_file.getframerate()
            duration = frames / float(rate)
        size_kb = out_path.stat().st_size / 1024
        print(f"  {path.stem}.wav  {duration:5.1f}s  {size_kb:6.0f} KB")

    print(
        "\nPronto. Exemplo de uso: uv run dentanote run "
        + str(args.out_dir / f"{transcripts[0].stem}.wav")
    )


if __name__ == "__main__":
    main()
