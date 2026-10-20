# PROMPT: DentaNote, assistente local de evolução clínica odontológica

## 0. Papel e contexto

Você é um engenheiro de software sênior em Python, com experiência em pipelines de IA local e software de saúde. Vai construir, de ponta a ponta, o projeto **DentaNote**, em um repositório novo, pronto para publicar no GitHub.

Contexto: o projeto é minha submissão ao Hacktoberfest 2026 "Open-Source AI Challenge, Week 3" no DEV (tema "Slow and Steady": construir algo com IA open-source que automatize uma tarefa que ninguém quer fazer). Sou cirurgião-dentista e desenvolvedor. Prazo de entrega: 25/10/2026. Os critérios de julgamento, em ordem, são: qualidade da escrita do post, relevância ao tema, criatividade, execução técnica e uso de tecnologia de parceiros (opcional).

**Ideia central:** o dentista grava a consulta (ou dita um resumo ao final). Um pipeline 100% local transcreve o áudio, extrai os dados clínicos de forma estruturada e gera a evolução clínica em texto, pronta para colar no prontuário.

**Por que open-source/local importa (isso precisa ficar demonstrável no projeto):**
1. Dados de pacientes nunca saem da máquina (LGPD, dado sensível de saúde).
2. Funciona sem internet.
3. Custo zero após a configuração.
4. Modelos trocáveis e ajustáveis.

## 1. Restrições inegociáveis

- **Nenhum dado real de paciente**, em nenhum lugar (código, testes, README, exemplos, commits). Toda demo usa dados 100% sintéticos, com nomes e cenários fictícios.
- **Nenhuma chamada a APIs externas em tempo de execução.** Após baixar os modelos, tudo funciona offline. Se algum recurso opcional precisar de rede (por exemplo, telemetria), ele deve vir desativado por padrão e ser claramente documentado.
- **Nenhum PHI em logs.** Logs e métricas registram apenas tempos, contagens e tamanhos, nunca transcrições nem texto clínico.
- **Saída é sempre RASCUNHO para revisão do profissional.** A interface e o texto gerado devem deixar isso explícito. O sistema nunca inventa informação: campo não mencionado no áudio fica `null` ou "não informado". Ele não faz diagnóstico, não sugere conduta e não preenche lacunas por inferência.
- Licença MIT. Código, comentários de código e nomes de variáveis em inglês. README, interface e textos clínicos em português do Brasil.
- Python 3.11+. Dependências mínimas e fixadas (pinned) em `pyproject.toml`.

## 2. Stack

- **Transcrição:** `faster-whisper` (modelo configurável; padrão `small`, com opção `medium`), idioma `pt`, VAD ativado. Funciona em CPU, usa GPU se disponível.
- **LLM local:** Gemma via **Ollama**, acessado pelo cliente HTTP local (`http://localhost:11434`). O nome do modelo vem de configuração (padrão: uma variante pequena de Gemma disponível no Ollama, como `gemma3:4b`; verifique com `ollama list`/biblioteca do Ollama qual é a versão de Gemma mais recente disponível e use-a como padrão, documentando a escolha). Usar saída estruturada (parâmetro `format` com JSON Schema) para forçar JSON válido.
- **Validação:** Pydantic v2.
- **Interface:** Streamlit (principal) + CLI com `typer` (secundária).
- **Testes:** `pytest`. **Lint/format:** `ruff`. **Tipos:** `mypy` (modo razoável, não precisa ser estrito).
- **CI:** GitHub Actions.
- **Gerenciador:** `uv` (ou pip, com instruções para ambos).

## 3. Estrutura do repositório

```
dentanote/
├── pyproject.toml
├── README.md                  # PT-BR, com GIF/prints, ver seção 9
├── LICENSE
├── .github/workflows/ci.yml
├── src/dentanote/
│   ├── __init__.py
│   ├── config.py              # settings via env/pydantic-settings
│   ├── transcribe.py          # faster-whisper wrapper
│   ├── extract.py             # chamada ao Ollama + parsing/validação
│   ├── schema.py              # modelos Pydantic (seção 4)
│   ├── prompts.py             # prompts do sistema e few-shot
│   ├── render.py              # JSON -> texto da evolução clínica
│   ├── pipeline.py            # orquestra: áudio/texto -> resultado + métricas
│   ├── metrics.py             # latência, tokens, tamanho (sem PHI)
│   ├── cli.py                 # typer
│   └── app.py                 # Streamlit
├── data/synthetic/
│   ├── transcripts/           # >= 12 transcrições sintéticas (txt)
│   ├── expected/              # JSON esperado para cada transcrição
│   └── audio/                 # opcional: áudios gerados via TTS offline
├── scripts/
│   ├── make_synthetic_audio.py  # gera áudio sintético offline (piper ou espeak-ng)
│   └── evaluate.py              # avaliação (seção 7)
├── tests/
└── docs/                      # prints, GIF, diagrama de arquitetura (mermaid)
```

## 4. Schema de dados (src/dentanote/schema.py)

Defina com Pydantic v2 e exporte o JSON Schema para o Ollama. Todos os campos clínicos são opcionais (`None` quando não mencionados).

```
ClinicalNote:
  chief_complaint: str | None            # queixa principal, nas palavras do paciente quando possível
  history: str | None                    # histórico relevante mencionado
  findings: list[str]                    # achados clínicos/radiográficos mencionados
  teeth: list[ToothRef]                  # dentes envolvidos
  procedures: list[Procedure]            # procedimentos realizados
  materials_anesthesia: list[str]        # anestésicos/materiais citados
  medications_prescribed: list[Medication]
  guidance_given: list[str]              # orientações ao paciente
  follow_up: str | None                  # retorno / próxima etapa
  uncertain_items: list[str]             # trechos ambíguos que o profissional deve conferir

ToothRef:   fdi_number: int (11-48 permanentes, 51-85 decíduos), surfaces: list[str] (M,D,O,V,L,P,I), note: str | None
Procedure:  name: str, tooth_fdi: list[int], details: str | None
Medication: name: str, dose: str | None, frequency: str | None, duration: str | None
```

Regras:
- Normalizar dentes para notação **FDI**. Se o áudio disser "dente 36", "primeiro molar inferior esquerdo" etc., converter. Se a conversão for ambígua, colocar em `uncertain_items`.
- Validar faixas de números FDI com validator do Pydantic. Descartar e registrar em `uncertain_items` qualquer número inválido.
- `uncertain_items` é obrigatório como mecanismo de segurança: tudo que o modelo não tem certeza vai para lá.

## 5. Comportamento do pipeline

1. **Entrada:** arquivo de áudio (wav/mp3/m4a/ogg), gravação pelo navegador (Streamlit `st.audio_input`) ou texto colado (para testar sem áudio).
2. **Transcrição:** `faster-whisper` com `language="pt"`, `vad_filter=True`. Retornar texto e duração do áudio. Prompt inicial opcional (`initial_prompt`) com vocabulário odontológico comum (nomes de procedimentos, "restauração", "endodontia", "profilaxia", "MOD", nomes de anestésicos) para melhorar o reconhecimento.
3. **Extração:** enviar a transcrição ao Gemma/Ollama com prompt de sistema rigoroso (seção 6), `temperature` baixa (0 a 0.2) e `format` = JSON Schema. Validar com Pydantic. Se a validação falhar, fazer **até 2 tentativas** de reparo (reenviando o erro de validação) e, se ainda falhar, retornar um resultado parcial com aviso claro. Nunca lançar exceção crua ao usuário.
4. **Renderização:** `render.py` transforma o JSON em texto corrido de evolução clínica, em PT-BR formal e conciso, de forma **determinística, por template, não por LLM**. Isso garante que nada seja inventado na etapa final. Seções ausentes são omitidas, nunca preenchidas com texto genérico. Se houver `uncertain_items`, anexar bloco "⚠ Conferir antes de salvar".
5. **Métricas:** registrar por execução: duração do áudio, tempo de transcrição, tempo de extração, tokens de prompt/resposta (vindos do Ollama), tempo total, modelo usado, número de tentativas de reparo. Gravar em `metrics.jsonl` local, sem texto clínico.

## 6. Prompt do sistema para extração (src/dentanote/prompts.py)

Escreva em PT-BR, com estas regras explícitas:
- "Você extrai informações de uma transcrição de consulta odontológica. Use SOMENTE o que está dito na transcrição."
- "Se uma informação não foi dita, use null ou lista vazia. É proibido inferir, completar ou supor."
- "Não faça diagnóstico nem sugira conduta."
- "Converta dentes para notação FDI. Se houver dúvida, adicione o trecho em uncertain_items."
- "Ignore conversa social e ruído irrelevante à evolução clínica."
- "Responda apenas com JSON válido conforme o schema."

Inclua 3 exemplos few-shot sintéticos (restauração, exodontia simples e profilaxia com orientação), cobrindo também um caso com informação ambígua que cai em `uncertain_items`. Os exemplos devem ser claramente fictícios.

## 7. Avaliação e comparação (essencial para o post)

Crie `scripts/evaluate.py` que roda o pipeline sobre `data/synthetic/transcripts` e compara com `data/synthetic/expected`:
- **Métricas de qualidade:** precisão/recall/F1 por campo (dentes FDI, procedimentos, medicamentos), taxa de JSON válido na primeira tentativa, taxa de alucinação (itens extraídos que não aparecem no esperado), uso correto de `uncertain_items`.
- **Métricas de desempenho:** latência média e p95 por etapa, tokens/s, uso de memória aproximado.
- **Comparação de modelos:** permitir rodar com 2 ou mais modelos do Ollama (ex.: dois tamanhos de Gemma) e gerar uma tabela comparativa em Markdown em `docs/results.md`. Isso demonstra a vantagem de "modelos trocáveis" do open-source.
- **Teste offline:** documente e automatize, quando possível, uma verificação de que o pipeline roda sem rede (ex.: instruções para desligar o Wi-Fi, mais um teste que bloqueia sockets externos com `pytest-socket` permitindo apenas localhost).
- Comparação com nuvem **apenas em termos conceituais no README/post** (privacidade, custo recorrente, dependência de internet), sem integrar nenhuma API de nuvem ao projeto.

## 8. Dados sintéticos

- Crie pelo menos **12 transcrições** fictícias variadas, em linguagem natural de consultório (hesitações, correções, termos coloquiais): restauração classe I/II, endodontia, exodontia, profilaxia/raspagem, urgência com dor, prescrição de analgésico/antibiótico, consulta de retorno, cenário com informação ambígua, cenário com número de dente falado de formas diferentes.
- Para cada uma, o JSON esperado em `expected/`.
- `scripts/make_synthetic_audio.py`: gera áudio dessas transcrições com TTS **offline** (piper ou espeak-ng, o que for mais simples de instalar), para a demo ponta a ponta. Documentar que o áudio é sintético.
- Nenhum nome real. Use nomes claramente fictícios (ex.: "Paciente Exemplo 01").

## 9. Interface (Streamlit)

- Título, aviso fixo: "Rascunho gerado por IA local. Revise antes de salvar no prontuário. Nenhum dado sai deste computador."
- Abas ou seções: (1) Entrada (upload, gravar, colar texto), (2) Transcrição editável, (3) Dados estruturados (editáveis), (4) Evolução clínica final com botão **Copiar**, (5) Métricas da execução.
- Indicador de status offline/local (mostra o modelo Ollama e o modelo Whisper em uso).
- Item de `uncertain_items` destacado visualmente.
- Botão "Carregar exemplo sintético" para a demo rodar em 1 clique.
- Tema simples, limpo, legível; sem dependência de CDN externo.
- A edição manual do usuário alimenta o texto final (o profissional é a autoridade final).

CLI (`typer`): `dentanote run audio.wav`, `dentanote text arquivo.txt`, `dentanote eval`, `dentanote doctor` (verifica se Ollama está rodando, se os modelos estão baixados, e se há GPU).

## 10. Qualidade, CI e GitHub

- Testes unitários: validação do schema (FDI), renderização determinística, parsing e reparo de JSON, normalização de dentes, ausência de PHI nos logs (teste que verifica que `metrics.jsonl` não contém a transcrição).
- Testes de integração: pipeline com transcrição sintética e um **cliente Ollama mockado**, para o CI não depender do modelo. Um teste marcado `@pytest.mark.slow` roda com Ollama real localmente.
- GitHub Actions (`ci.yml`): ruff, mypy, pytest (sem os testes lentos) em Python 3.11 e 3.12. Opcional: workflow que gera o relatório de avaliação com o cliente mockado.
- Commits pequenos e semânticos (conventional commits). Issues/labels iniciais e `CONTRIBUTING.md` curto, pois o projeto deve convidar contribuições (ex.: outras especialidades, outros idiomas).
- `SECURITY.md` curto explicando a política de dados: "nunca abra issues com dados reais de pacientes".

## 11. README.md (PT-BR), conteúdo obrigatório

1. Gancho em 2 linhas: o problema (tempo gasto em prontuário) e a solução.
2. GIF/vídeo curto da demo.
3. **Por que local e open-source** (privacidade/LGPD, offline, custo, modelos trocáveis), em linguagem direta.
4. Como funciona (diagrama mermaid do fluxo áudio → Whisper → Gemma → schema → template → texto).
5. Instalação passo a passo (Ollama, modelos, `uv sync`, rodar).
6. Uso (CLI e interface).
7. Resultados da avaliação (tabela de `docs/results.md`) e limitações honestas.
8. **Aviso legal e ético**: é ferramenta de apoio, o profissional revisa tudo; não substitui julgamento clínico; não use com dados reais sem avaliação de conformidade com a LGPD e com as normas do conselho profissional.
9. Roadmap e como contribuir.

## 12. Ordem de trabalho (execute em fases, com commit ao final de cada uma)

- **Fase 1:** esqueleto do repo, `pyproject.toml`, config, schema e testes do schema.
- **Fase 2:** `transcribe.py` + `extract.py` + prompts, rodando via CLI com texto sintético. Critério: JSON válido para ≥ 90% das transcrições sintéticas.
- **Fase 3:** `render.py` determinístico, `pipeline.py` e métricas.
- **Fase 4:** dados sintéticos completos + `evaluate.py` + comparação entre modelos.
- **Fase 5:** interface Streamlit + comando `doctor`.
- **Fase 6:** CI, README, docs, diagrama, polimento.
- **Fase 7:** gerar rascunho do post para o DEV em `docs/post_draft.md` (seção 13).

Ao fim de cada fase: rode lint e testes, mostre um resumo curto do que foi feito e o que falta, e aponte decisões de design que tomou. Se alguma instrução for ambígua, escolha a opção mais segura em termos de privacidade, registre a decisão no README e siga em frente sem travar.

## 13. Rascunho do post (docs/post_draft.md)

Escreva em PT-BR, tom pessoal e direto (a escrita é o critério de maior peso). Estrutura:
1. **O que construí e que esforço ele economiza** (com número: minutos economizados por consulta, baseado nas medições reais da avaliação, sem inventar estatística).
2. **Demo** (onde inserir GIF/vídeo).
3. **Por que open-source/local venceu o fechado aqui:** privacidade, offline, custo, trocar de modelo e comparar (use a tabela real de resultados).
4. **Como foi construído** (decisões-chave: saída estruturada, template determinístico para não alucinar, `uncertain_items`).
5. **O que deu errado e limitações**, com honestidade.
6. **O que vem a seguir** e convite à contribuição.
Inclua no final as tags `#devchallenge` e `#hf26challenge`. Deixe marcadores `[INSERIR: ...]` onde eu precise colocar GIF, links ou números reais que só eu posso medir.

## 14. Critérios de aceite finais

- [ ] `uv sync && dentanote doctor` funciona em máquina limpa seguindo o README.
- [ ] Demo ponta a ponta com áudio sintético gera nota clínica em CPU comum em tempo razoável (registre o tempo medido).
- [ ] Funciona com a internet desligada.
- [ ] Nenhum dado real; nenhum PHI em logs; teste automatizado cobrindo isso.
- [ ] Texto final nunca contém informação ausente do áudio (revisar com os casos sintéticos).
- [ ] CI verde.
- [ ] README completo; `docs/results.md` e `docs/post_draft.md` gerados.
