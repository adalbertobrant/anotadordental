# Rascunho de post para o DEV — DentaNote

> Status: **rascunho revisável**. Números abaixo vêm das medições reais em
> `docs/results.md` e `metrics.jsonl`. Marcadores `[INSERIR: ...]` marcam o que
> só você pode colocar (GIF, links do repositório, tempos da sua própria rotina).

---

Eu atendo, dicto a evolução da consulta e ainda levo tempo montando a nota
estruturada no prontuário — campos, números dentários, o diário todo. O
DentaNote é a ferramenta que escrevi para cortar essa etapa: **áudio entra,
nota clínica estruturada sai**, rodando 100% local, sem um único dado saindo da
minha máquina.

## 1. O que construí e que esforço ele economiza

O pipeline inteiro — transcrição com Whisper, extração com Gemma via Ollama,
validação de esquema e renderização — levou **11,2 segundos** para transformar
um áudio de 30 segundos em nota completa (transcrição: 7,7 s; extração: 2,1 s;
renderização: subproduto, não medido porque é template determinístico).

O Whisper pequeno em CPU transcreve ~3,8× mais rápido que o tempo real. Ou
seja, um ditado de 3 minutos viraria texto em cerca de 45 s, mais ~2 s de
extração — **menos de um minuto para uma nota que eu ditaria inteira**.

Meu próprio tempo de digitação: escrever uma evolução estruturada à mão leva
cerca de **10 minutos**. Contra o "menos de um minuto" do pipeline, são **~9
minutos de volta por consulta** — e ao longo de um dia cheio de atendimentos,
esse tempo compõe em mais do que uma consulta inteira de trabalho.

## 2. Demo

▶ **[Vídeo da demo (2 min)](https://github.com/adalbertobrant/anotadordental/blob/main/video/dentanote-demo.webm)**
— `dentanote run consulta.wav` no terminal e a interface Streamlit abrindo com a
nota pronta + aviso fixo de rascunho.

A demo real que rodei: dois casos sintéticos, do áudio à nota, com tempo
registrado em `metrics.jsonl` (só durações e contagens — zero PHI, e há teste
automatizado garantindo isso).

## 3. Por que open-source e local venceu o fechado aqui

- **Privacidade/LGPD:** o áudio da consulta é dado de paciente. No pipeline
  local ele vai do microfone para o Whisper na mesma máquina. Nenhuma chamada
  de rede além de `localhost:11434`. Não é "confie em nós" — é arquitetura.
- **Offline:** funciona com a internet desligada (e o pytest roda com sockets
  bloqueados justamente para provar isso).
- **Custo:** Ollama + modelos abertos, sem fatura por token.
- **Trocar de modelo e comparar:** eu comparei dois no mesmo corpus de 12
  casos sintéticos:

| Modelo | Precisão | Recall | F1 | Alucinação | `uncertain_items` | Latência média |
| --- | --- | --- | --- | --- | --- | --- |
| `gemma4:e4b` | 0,92 | 0,89 | 1,00 | 11,1% | 100% | 1,70 s |
| `gemma3:4b` | 0,75 | 0,65 | 0,92 | 31,8% | 100% | 5,59 s |

Os dois geraram JSON **válido em 100% das execuções na primeira tentativa**.
Os dois erraram juntos no mesmo caso (`urgencia_dor` previu dente 37 em vez
de 47 — o modelo "escolheu" um vizinho na arcada).

[Tabela acima: copiada de `docs/results.md`; reler o relatório gerado antes de
publicar caso você reexecute a avaliação.]

## 4. Como foi construído

Três decisões que evitam o modo clássico de um LLM odontológico inventar
coisa:

1. **Saída estruturada pelo `format` (JSON Schema) do Ollama** — constrained
   decoding põe tokens fora do esquema com probabilidade zero. Mesmo assim o
   cliente valida com Pydantic, porque modelo "thinking" pode ignorar o esquema
   com `think=true` (sim, isso acontece — documentado no ADR-001).
2. **Template determinístico, nunca LLM na última etapa.** O texto final só
   transcreve campos já validados. Se o campo não veio do áudio, ele não
   aparece — não tem "alucinação" onde deveria haver silêncio.
3. **`uncertain_items` como válvula de segurança.** Número FDI inválido? Dente
   falado de jeito ambíguo? Vai listado para o profissional conferir, nunca
   resolvido em silêncio. Num dos meus casos, um FDI 56 (molar do quadrante
   errado) foi descartado e apareceu exatamente assim.

Estrutura: 7 fases, commit por fase, lint+testes antes de cada um (150 testes
hoje), ADRs curtos em `docs/AGILE.md`.

## 5. O que deu errado e limitações (com honestidade)

- **Avaliação é sobre 12 casos sintéticos**, com transcrições geradas por mim
  e áudio sintético (piper-tts). Não é estudo clínico, não tem poder
  estatístico, e o discurso real é bem mais sujo.
- **Alucinação não é zero:** o `gemma4:e4b` inventou algum item em 11,1% dos
  casos (o `gemma3:4b`, em 31,8%). Por isso a saída é **sempre rascunho
  revisável** — é um pré-preenchimento, não um prontuário assinado.
- **Erro troca de vizinho:** 37 → 47 no caso de urgência. O framework não
  pega isso sozinho; só a revisão humana pega.
- **CUDA do Whisper estava quebrada na minha máquina** (`libcublas.so.12`
  ausente) — o fallback para CPU funcionou ao vivo, mas é um lembrete de que
  "local" também significa "você é o suporte técnico".
- **Nenhum dado real foi usado**, por decisão e por regra. Testar com dados
  reais exige conformidade com LGPD e com as normas do conselho — fora do
  escopo deste projeto.

## 6. O que vem a seguir e convite à contribuição

- **Edição manual dos campos na UI** antes do texto final — o profissional
  ajusta item a item no Streamlit e só então renderiza o rascunho.
- **Mais vozes e idiomas de TTS** em `scripts/make_synthetic_audio.py`
  (corpus de áudio sintético em ES/EN para testar o pipeline bilíngue).
- **Corpus maior**: empacotar mais cenários sintéticos (implantodontia,
  periodontia, ortodontia) com o `expected/` correspondente — o
  `scripts/evaluate.py` já mede o impacto de cada um.

O repositório está aberto com licença MIT: se você trabalha com evolução
clínica e quiser malhar o vocabulário de procedimentos ou adicionar casos do
seu dia a dia (obrigatoriamente sintéticos), as issues e o `CONTRIBUTING.md`
estão lá.

[Repositório no GitHub](https://github.com/adalbertobrant/anotadordental) ·
[Seção de aviso legal e ético do README](https://github.com/adalbertobrant/anotadordental#8-aviso-legal-e-ético)

---

`#devchallenge` `#hf26challenge`
