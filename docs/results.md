# Resultados da avaliação (DentaNote)

Gerado por `scripts/evaluate.py` sobre as 12 transcrições sintéticas de `data/synthetic/transcripts`, comparando com `data/synthetic/expected/`.

## Qualidade

| Modelo | JSON válido 1ª tentativa | Precisão (F1) dentes FDI | F1 procedimentos | F1 medicamentos | Taxa de alucinação | Uso de `uncertain_items` | Reparos (média) |
| --- | --- | --- | --- | --- | --- | --- | --- |
| `gemma4:e4b` | 100% | 0.92 | 0.89 | 1.00 | 11.1% | 100% | 0.00 |
| `gemma3:4b` | 100% | 0.75 | 0.65 | 0.92 | 31.8% | 100% | 0.00 |

## Desempenho

| Modelo | Latência média (extração) | p95 (extração) | p95 (total) | Tokens/s | Tokens totais |
| --- | --- | --- | --- | --- | --- |
| `gemma4:e4b` | 1.70 s | 2.03 s | 2.03 s | 77.9 | 18656 |
| `gemma3:4b` | 5.59 s | 6.52 s | 6.52 s | 23.9 | 18764 |

Memória máxima do processo (RSS): **50 MB** (avaliação completa).

### Como ler

- **Taxa de alucinação** = itens extraídos que não existem no resultado esperado (1 - precisão). Quanto mais perto de 0%, melhor.
- **Uso de `uncertain_items`** = casos em que o esperado marcava incerteza e o modelo também marcou (deveria ser 100%).
- Os campos são comparados por conjuntos normalizados (acentos/caixa removidos); dentes, pela notação FDI.
- Resultados com dados 100% sintéticos — nenhum paciente real foi usado.
