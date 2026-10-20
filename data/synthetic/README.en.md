# Synthetic data (transcripts and expected extractions)

> 🇧🇷 [Versão em português](README.md).

> **All data in this directory is 100% fictional.**
> The transcripts were written by hand to test the pipeline. There is no real
> patient, no real name, no real medical record, no real clinical data in any
> file here. The "patients" are called **Sample Patient 01** ...
> **Sample Patient 12** on purpose, so it is obvious they are fictional.

## Structure

```
data/synthetic/
├── transcripts/   # 12 transcripts in PT-BR (text only, UTF-8)
├── expected/      # expected JSON (ideal extraction) per transcript
└── README.md      # this file
```

- `transcripts/<slug>.txt` — natural clinic language: hesitations,
  corrections, colloquial terms and pauses. 40 to 140 words each.
- `expected/<slug>.json` — the ideal extraction per the Pydantic schema
  `ClinicalNote` (`src/dentanote/schema.py`). Contains **only** information
  that literally appears in the transcript. An unmentioned field stays `null`
  or an empty list — nothing is inferred, nothing is diagnosed.

## The 12 scenarios

| # | Slug | What the transcript covers |
|---|------|---------------------------|
| 1 | `restauracao_classe_I` | Class I composite restoration on 36, local anesthesia and post-op guidance |
| 2 | `restauracao_classe_II` | Class II restoration on 26 with multiple surfaces (O, M, D), matrix and wedge |
| 3 | `endodontia` | Root canal start on 46: access, intracanal calcium hydroxide medication and recall |
| 4 | `exodontia_simples` | Simple extraction of 18 (wisdom tooth), gauze hemostasis and guidance |
| 5 | `profilaxia_raspagem` | Prophylaxis with supragingival scaling and hygiene guidance |
| 6 | `urgencia_dor` | Pain for days, exam and urgent procedure, **no invented diagnosis** |
| 7 | `prescricao_analgesico` | Analgesic with dose, frequency and duration explicitly dictated |
| 8 | `prescricao_antibiotico` | Antibiotic with dictated dosage, together with the performed procedure |
| 9 | `retorno` | Recall visit assessing healing/result, no new procedure |
| 10 | `informacao_ambigua` | Unintelligible passages and vague information — everything must land in `uncertain_items`; nothing clinical may be inferred |
| 11 | `dente_falado_de_formas` | The same tooth named in different ways (normalizes to 36) + an invalid dictated number ("tooth ninety-one") |
| 12 | `dente_deciduo` | Child, primary tooth (64), extraction of a deciduous tooth with explicit "baby tooth" mention |

## How to validate

```bash
export PATH="$HOME/.local/bin:$PATH"
cd /home/adalberto/git/anotadordental
uv run python - <<'EOF'
import json, pathlib
from dentanote.schema import ClinicalNote
base = pathlib.Path("data/synthetic")
transcripts = sorted(base.glob("transcripts/*.txt"))
assert len(transcripts) == 12, len(transcripts)
for t in transcripts:
    exp = base / "expected" / (t.stem + ".json")
    assert exp.exists(), f"missing {exp.name}"
    note = ClinicalNote.model_validate(json.loads(exp.read_text()))
    txt = t.read_text(encoding="utf-8")
    assert len(txt.split()) >= 30, t.name
    print("OK", t.name, len(txt.split()), "words | uncertain:", len(note.uncertain_items))
print("ALL OK")
EOF
```

## Usage

- `scripts/evaluate.py` compares pipeline output with `expected/` and computes
  per-field precision/recall/F1, hallucination rate and `uncertain_items`
  usage.
- `scripts/make_synthetic_audio.py` (optional) generates **synthetic** audio
  from these transcripts with offline TTS (piper or espeak-ng) for the
  end-to-end demo. The audio is also synthetic and represents nobody.

## Content rules

- Tooth numbers only in valid FDI notation: 11–48 (permanent) and 51–85
  (deciduous). Invalid numbers dictated in audio go to `uncertain_items`,
  never to `teeth`/`procedures`.
- Surfaces in uppercase, only `M`, `D`, `O`, `V`, `L`, `P`, `I`.
- `uncertain_items` is filled whenever there is an unintelligible passage,
  vague information or an invalid number; otherwise `[]`.
- No diagnosis is invented: the JSONs describe only what was said and done in
  the transcript.
