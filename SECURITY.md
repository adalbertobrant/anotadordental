# Segurança e política de dados — DentaNote

## Regra número um: nunca com dados reais de pacientes

**Não abra issues, pull requests, discussões, logs, prints ou anexos contendo
dados reais de pacientes (PHI).** Em saúde isso é dado sensível protegido pela
LGPD; aqui é também uma regra de projeto: o repositório só pode conter dados
100% sintéticos (`data/synthetic/`, "Paciente Exemplo 01", cenários fictícios).

Se você acidentalmente expuser um dado real:

1. Não tente "apagar por cima" com um novo commit — avise imediatamente.
2. Abra um issue **sem repetir o dado** ou contate os mantenedores diretamente
   (aba **Security** → *Report a vulnerability* do repositório no GitHub).
3. A manutenção fará *rewrite* do histórico se necessário e pedirá que você
   rode `git fetch && git reset --hard` (coordenação será combinada no canal
   privado).

## Escopo

O DentaNote é um programa **local**: não há servidor, conta, telemetria ou
chamada a API externa em tempo de execução. As únicas comunicações de rede são:

| Comunicação | Quando | Redes externas? |
| --- | --- | --- |
| `http://localhost:11434` (Ollama) | extração | não — sempre localhost |
| Download de modelos (Ollama/HuggingFace) | primeira instalação | sim, uma vez; depois tudo offline |
| Qualquer outra coisa | nunca | — |

Vulnerabilidades que violem esses princípios (ex.: um pedido HTTP saindo da
máquina com texto clínico) são consideradas **críticas**.

## Como reportar

- Use o formulário de *security advisory* do GitHub do repositório (ou, se
  indisponível, um issue com a palavra `[segurança]` e **sem** dados reais).
- Inclua: versão (`dentanote version`), sistema operacional, passos de
  reprodução com **dados sintéticos** e o comportamento esperado.

## Versões suportadas

| Versão | Suporte |
| --- | --- |
| 0.1.x | ativo |

Correções são publicadas na branch `main`; releases com tag quando houver
mudança relevante para a política de dados.
