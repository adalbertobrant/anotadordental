# Dados sintéticos (transcrições e extrações esperadas)

> **Todos os dados deste diretório são 100% fictícios.**
> As transcrições foram escritas à mão para testes do pipeline. Não há nenhum
> paciente real, nenhum nome real, nenhum prontuário real, nenhum dado clínico
> real em qualquer arquivo aqui. Os "pacientes" se chamam
> **Paciente Exemplo 01** ... **Paciente Exemplo 12** de propósito, para ser
> óbvio que são fictícios.

## Estrutura

```
data/synthetic/
├── transcripts/   # 12 transcrições em PT-BR (só texto, UTF-8)
├── expected/      # JSON esperado (extração ideal) para cada transcrição
└── README.md      # este arquivo
```

- `transcripts/<slug>.txt` — linguagem natural de consultório: hesitações,
  correções, termos coloquiais e pausas. Entre 40 e 140 palavras cada.
- `expected/<slug>.json` — extração ideal conforme o schema Pydantic
  `ClinicalNote` (`src/dentanote/schema.py`). Contém **somente** informação que
  aparece literalmente na transcrição. Campo não mencionado fica `null` ou
  lista vazia — nada é inferido, nada é diagnosticado.

## Os 12 cenários

| # | Slug | O que a transcrição cobre |
|---|------|---------------------------|
| 1 | `restauracao_classe_I` | Restauração em resina classe I no 36, anestesia local e orientações pós-operatórias |
| 2 | `restauracao_classe_II` | Restauração classe II no 26 com várias superfícies (O, M, D), matriz e cunha |
| 3 | `endodontia` | Início de canal no 46: abertura, medicação intracanal com hidróxido de cálcio e retorno |
| 4 | `exodontia_simples` | Exodontia simples do 18 (siso), hemostasia com gaze e orientações |
| 5 | `profilaxia_raspagem` | Profilaxia com raspagem supragengival e orientação de higiene |
| 6 | `urgencia_dor` | Dor há dias, exame e procedimento de urgência, **sem diagnóstico inventado** |
| 7 | `prescricao_analgesico` | Analgésico com dose, frequência e duração ditados explicitamente |
| 8 | `prescricao_antibiotico` | Antibiótico com posologia dita, junto com o procedimento realizado |
| 9 | `retorno` | Consulta de retorno avaliando cicatrização/resultado, sem procedimento novo |
| 10 | `informacao_ambigua` | Trechos não inteligíveis e informação vaga — tudo deve cair em `uncertain_items`; nada clínico pode ser inferido |
| 11 | `dente_falado_de_formas` | O mesmo dente citado de formas diferentes (normaliza para 36) + número inválido dito ("dente noventa e um") |
| 12 | `dente_deciduo` | Criança, dente de leite (64), exodontia em dente deciduo com menção explícita de "dente de leite" |

## Como validar

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

## Uso

- `scripts/evaluate.py` compara a saída do pipeline com `expected/` e calcula
  precisão/recall/F1 por campo, taxa de alucinação e uso de `uncertain_items`.
- `scripts/make_synthetic_audio.py` (opcional) gera áudio **sintético** dessas
  transcrições com TTS offline (piper ou espeak-ng) para a demo ponta a ponta.
  O áudio também é sintético e não representa nenhuma pessoa.

## Regras de conteúdo

- Números de dente apenas em notação FDI válida: 11–48 (permanentes) e
  51–85 (decíduos). Números inválidos ditos em áudio vão para
  `uncertain_items`, nunca para `teeth`/`procedures`.
- Superfícies em maiúsculas, apenas `M`, `D`, `O`, `V`, `L`, `P`, `I`.
- `uncertain_items` é preenchido sempre que houver trecho não inteligível,
  informação vaga ou número inválido; nos demais casos, `[]`.
- Nenhum diagnóstico é inventado: os JSONs descrevem apenas o que foi
  dito e feito na transcrição.
