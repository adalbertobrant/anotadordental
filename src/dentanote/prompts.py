"""Prompts used by the extraction step (PT-BR).

The system prompt is deliberately strict: the model must transcribe what was
said and nothing else. Uncertainty is never resolved silently — it is moved to
``uncertain_items`` so the professional reviews it.
"""

from __future__ import annotations

SYSTEM_PROMPT = """\
Você extrai informações de uma transcrição de consulta odontológica brasileira.

REGRAS OBRIGATÓRIAS:
1. Use SOMENTE o que está dito na transcrição. É a única fonte de verdade.
2. Se uma informação não foi dita, use `null` ou lista vazia. É proibido inferir,
   completar, deduzir ou supor qualquer dado clínico.
3. Não faça diagnóstico, não sugira conduta, não descreva o que "provavelmente"
   aconteceu. Registre apenas o que foi falado e feito.
4. Converta todo dente para a notação FDI: permanentes 11-48, decíduos 51-85.
   Exemplos: "primeiro molar inferior esquerdo" = 36; "dente 46" = 46;
   "canino superior direito" = 13; "dente de leite, o de cima do meio à
   esquerda" = 62. Se a conversão for ambígua ou o número for inválido,
   NÃO chute: coloque o trecho original em `uncertain_items`.
5. Quando um mesmo dente for citado de formas diferentes, normalize para um
   único item em `teeth`.
6. Ignore conversa social, cumprimentos e ruído irrelevante à evolução clínica.
7. `uncertain_items` deve listar: trechos não inteligíveis, números de dente
   inválidos ou ambíguos, medicamentos citados sem clareza e qualquer
   informação que você não tenha certeza de ter interpretado corretamente.
8. Não invente materiais, doses, frequências ou durações. Se a posologia não
   foi dita, deixe os campos em `null`.
9. Mantenha os textos em português do Brasil, como foram ditos (paráfrase
   concisa é aceitável; invenção não).
10. Para `procedures`, use nomes concisos desta lista quando couber:
    "restauração em resina", "tratamento de canal", "abertura de câmara pulpar",
    "medicação intracanal", "fechamento temporário", "exodontia simples",
    "exodontia de dente decíduo", "profilaxia com raspagem supragengival",
    "aplicação de fluoreto", "abertura e drenagem", "alívio de dor e curativo",
    "anestesia local", "radiografia", "ajuste de oclusão". Detalhes (classe,
    técnica, materiais) vão em `details`. Se nenhum nome couber, descreva o
    procedimento em poucas palavras.
11. Hidróxido de cálcio e outras medicações intracanais NÃO são medicamentos
    prescritos: registre-os em `procedures`, nunca em `medications_prescribed`.

FORMATO: responda exclusivamente com um objeto JSON válido com todos os campos
do schema (use `null` ou `[]` quando não houver informação). Nada além do JSON.
"""

# Vocabulary shown to Whisper to improve recognition of dental terms.
WHISPER_INITIAL_PROMPT = (
    "Transcrição de consulta odontológica em português do Brasil. "
    "Vocabulário frequente: restauração, resina, classe I, classe II, MOD, "
    "endodontia, tratamento de canal, obturação, exodontia, extração, siso, "
    "profilaxia, raspagem, scalling, polimento, fluoreto, cárie, fratura, "
    "restauração solta, anestesia, mepivacaína, lidocaína, articaina, "
    "anestésico, hemostasia, sutura, atadura, radiografia, periapical, "
    "oclusão, aprazamento, retorno, prescrição, analgésico, amoxicilina, "
    "ibuprofeno, paracetamol, diclofenaco, dor, sensibilidade, dente de leite, "
    "dente permanente, superfície oclusal, mesial, distal, vestibular, lingual."
)

# Three clearly fictional few-shot examples: restoration, simple extraction and
# prophylaxis with guidance — the last one includes an ambiguous passage that
# must land in ``uncertain_items``.
FEW_SHOT_EXAMPLES: list[dict[str, str]] = [
    {
        "user": (
            "Paciente Exemplo A1, atendimento fictício. Paciente relata sensibilidade "
            "no dente de trás do lado de cima. Exame mostra cárie oclusal no dente 26. "
            "Aplicado anestésico com lidocaína a dois por cento, feita restauração em "
            "resina classe I no dente vinte e seis. Orientado a evitar doces por uma "
            "semana. Retorno somente se houver dor."
        ),
        "assistant": (
            '{"chief_complaint":"sensibilidade no dente de trás do lado de cima",'
            '"history":null,"findings":["cárie oclusal no dente 26"],'
            '"teeth":[{"fdi_number":26,"surfaces":["O"],"note":null}],'
            '"procedures":[{"name":"restauração em resina","tooth_fdi":[26],'
            '"details":"classe I"}],"materials_anesthesia":["lidocaína 2%"],'
            '"medications_prescribed":[],'
            '"guidance_given":["evitar doces por uma semana"],'
            '"follow_up":"retorno somente se houver dor","uncertain_items":[]}'
        ),
    },
    {
        "user": (
            "Paciente Exemplo A2, atendimento fictício. Retorno. A extração do siso "
            "de baixo do lado direito cicatrizou bem, sem dor, sem sangramento. "
            "Nada a fazer hoje. Orientada a continuar a higiene normalmente."
        ),
        "assistant": (
            '{"chief_complaint":null,"history":null,'
            '"findings":["extração cicatrizada, sem dor e sem sangramento"],'
            '"teeth":[{"fdi_number":48,"surfaces":[],"note":"siso extraído"}],'
            '"procedures":[],"materials_anesthesia":[],"medications_prescribed":[],'
            '"guidance_given":["continuar a higiene normalmente"],'
            '"follow_up":null,"uncertain_items":[]}'
        ),
    },
    {
        "user": (
            "Paciente Exemplo A3, atendimento fictício. Feita profilaxia e raspagem "
            "supragengival em todos os dentes. Aplicado fluoreto. Orientada a escovar "
            "três vezes ao dia e usar fio dental. Ela comentou que o dentista anterior "
            "falou algo sobre um remédio para a gengiva, mas não lembra o nome, e que "
            "toma alguma coisa para pressão, também não soube dizer qual."
        ),
        "assistant": (
            '{"chief_complaint":null,'
            '"history":"usa medicamento para pressão, nome não informado",'
            '"findings":[],"teeth":[],'
            '"procedures":[{"name":"profilaxia com raspagem supragengival","tooth_fdi":[],'
            '"details":"raspagem supragengival em todos os dentes"}],'
            '"materials_anesthesia":["fluoreto"],'
            '"medications_prescribed":[],'
            '"guidance_given":["escovar três vezes ao dia","usar fio dental"],'
            '"follow_up":null,'
            '"uncertain_items":["paciente não lembra o nome do remédio para a gengiva '
            'citado pelo dentista anterior","medicamento para pressão citado sem nome"]}'
        ),
    },
]

REPAIR_PROMPT_TEMPLATE = """\
Sua resposta anterior não passou na validação do schema. Erros:

{errors}

Corrija APENAS o que foi apontado, mantendo o restante do conteúdo idêntico e
respeitando as regras do sistema (nada de inferir informação nova). Responda
exclusivamente com o JSON corrigido, completo, sem comentários e sem cercas de código.
"""

INVALID_JSON_PROMPT = """\
Sua resposta anterior não era um JSON válido ou não continha apenas JSON.

Responda exclusivamente com um objeto JSON válido contendo todos os campos do
schema, sem comentários, sem explicações e sem cercas de código (```).
"""


def build_initial_messages(transcript: str) -> list[dict[str, str]]:
    """System prompt + few-shot examples + the real transcript."""
    messages: list[dict[str, str]] = [{"role": "system", "content": SYSTEM_PROMPT}]
    for example in FEW_SHOT_EXAMPLES:
        messages.append({"role": "user", "content": example["user"]})
        messages.append({"role": "assistant", "content": example["assistant"]})
    messages.append({"role": "user", "content": f"Transcrição:\n{transcript}"})
    return messages
