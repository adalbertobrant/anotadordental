# Como gravar o GIF da demo do DentaNote

Tutorial para produzir o vídeo curto da demo que o post do DEV pede (marcador
`[INSERIR: GIF ou vídeo curto da demo ...]` em `docs/post_draft.md` e no rascunho
publicado no DEV).

## O que é e por quê

O GIF (ou vídeo) da demo é a gravação da tela mostrando o DentaNote funcionando:
o terminal rodando os comandos e a interface abrindo com a nota pronta. No editor
do DEV, você arrasta o arquivo para cima do texto no lugar do marcador e ele vira
um `<img>`/vídeo embutido. Serve para o leitor (e o julgador do Hacktoberfest
Open-Source AI Challenge: Week 3) ver que o negócio funciona de verdade, sem
precisar clonar o repositório.

## Roteiro da gravação (10–20 segundos)

1. No terminal, a partir da raiz do projeto:

   ```bash
   uv run dentanote doctor          # mostra os ✓ de Ollama/modelos
   uv run dentanote run data/synthetic/audio/restauracao_classe_I.wav
   ```

   A nota clínica sai impressa no terminal.

2. Tela da interface Streamlit com a nota renderizada e o **aviso fixo de
   rascunho** visível:

   ```bash
   uv run streamlit run src/dentanote/app.py
   ```

Os 12 WAVs sintéticos da demo estão em `data/synthetic/audio/`
(`restauracao_classe_I.wav`, `urgencia_dor.wav`, etc.). São 100% sintéticos —
nenhum dado de paciente aparece na gravação.

## Opção A — gravador nativo do GNOME + ffmpeg (sem instalar nada)

Funciona em GNOME sobre Wayland (o padrão nas distros atuais).

1. `Ctrl+Alt+Shift+R` inicia a gravação da tela inteira (ícone de gravação no
   canto). Rode o roteiro acima; a mesma combinação para. O arquivo `.webm` vai
   para `~/Vídeos/`.
2. Converta para GIF com paleta de cores (sem a paleta, o GIF fica com bandas
   feias):

   ```bash
   cd ~/Vídeos
   ffmpeg -i Screencast*.webm \
     -vf "fps=12,scale=1000:-1:flags=lanczos,palettegen" palette.png
   ffmpeg -i Screencast*.webm -i palette.png \
     -lavfi "fps=12,scale=1000:-1:flags=lanczos[x];[x][1:v]paletteuse" \
     dentanote-demo.gif
   ```

3. Confira o tamanho:

   ```bash
   ls -lh dentanote-demo.gif
   ```

   Acima de ~10 MB o GIF pesa na página. Corte o começo com `-ss 3` (pula 3 s),
   o fim com `-t 20` (duração máxima de 20 s), ou reduza com
   `fps=10,scale=800:-1`.

## Opção B — Kooha (interface gráfica, mais controlável)

```bash
flatpak install flathub io.github.seadve.Kooha
```

O Kooha grava área selecionada ou janela, com cursor visível — bom para capturar
**só a janela do terminal** (mais legível que a tela inteira). Salva em WebM/MP4
e você faz o mesmo `ffmpeg` da Opção A a partir do passo 2.

## Opção C — terminal "de filme" (asciinema) + Streamlit separado

Visual mais bonito de terminal, com fonte nítida em qualquer tamanho de tela:

```bash
pipx install asciinema agg   # agg é o renderizador oficial para GIF
asciinema rec demo.cast      # grave doctor + run; Ctrl+C encerra
agg demo.cast dentanote-terminal.gif --fps 2 --theme monokai
```

Limitação: captura só o terminal. Combine com um GIF curto da interface
(Opção A/B para o pedaço do Streamlit) ou use só a Opção A se preferir um
arquivo único.

## Alternativa: nem é GIF

O editor do DEV aceita **arrastar um `.mp4`** também: um vídeo de 1080p de 15 s
pesa ~2 MB contra 8–12 MB de GIF equivalente, e ainda permite áudio (dá para
deixar o som do Whisper trabalhando). O marcador `[INSERIR: ...]` funciona igual.

## Dicas que fazem diferença no post

- **Fonte grande:** aumente o zoom do terminal (`Ctrl++`) antes de gravar — em
  GIF de coluna estreita, texto de 12 px é ilegível.
- **Comece com o comando já na linha** (ou digite devagar): o leitor precisa
  entender causa e efeito, não só ver texto rolando.
- **Encurte o prompt:** grave a partir de `~/git/anotadordental` com prompt
  curto, por exemplo:

  ```bash
  PROMPT='dentanote $ ' bash
  ```

- **Mostre o aviso de rascunho** na interface — é o argumento ético do projeto
  virando imagem.
- **Segurança:** os áudios são 100% sintéticos, então não há PHI para esconder.
  Ainda assim, rode `git status` antes para não gravar caminhos de arquivos que
  você não quer expor.

## Depois de gravar

1. Publique o arquivo no rascunho do DEV (arraste no lugar do marcador), ou
   entregue o caminho para o agente fazer o `update_article` inserindo-o.
2. O rascunho no DEV está em:
   <https://dev.to/adalbertobrant/dentanote-evolucao-clinica-odontologica-com-gemma-local-sem-audio-saindo-do-consultorio-1e0b-temp-slug-7847687/edit>
3. Prazo do desafio Week 3 ("Slow and Steady"): **25/10, 23h59 PDT**.
