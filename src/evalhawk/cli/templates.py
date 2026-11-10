"""Files written by ``evalhawk init``: a runnable quickstart project."""

CONFIG = """\
# EvalHawk configuration. Docs: https://evalhawk.github.io/evalhawk/
version = 1

[project]
name = "support-bot"
store = ".evalhawk/eval.db"          # keep on a local disk (not a cloud-synced folder)

# The app being evaluated. Here: the Python function answer() in app.py.
[target]
type = "callable"
callable = "app:answer"
# Other targets:
#   type = "http"; url = "https://bot.internal/chat"; body = { message = "{{input}}" }
#   answer_path = "$.reply"; headers = { Authorization = "Bearer ${BOT_TOKEN}" }
#   type = "openai_compatible"; base_url = "http://localhost:11434/v1"; model = "llama3.2"
#   type = "recorded"             # answers already in the dataset's "output" column

[splits]
salt = "v1"                           # changing the salt creates a brand-new split

# ----------------------------------------------------------------- criteria
# Code checks: exact and free, no AI needed.
[[criteria]]
name = "not_empty"
check = { type = "not_empty" }

[[criteria]]
name = "concise"
check = { type = "max_words", value = 60 }

[[criteria]]
name = "no_personal_data"
check = { type = "pii" }

# LLM-judged checks: need a judge model (see [judges.local]).
[[criteria]]
name = "correctness"
template = "correctness"              # built-in: compares with the reference answer

[[criteria]]
name = "polite"
question = "Is the answer polite and professional?"   # your own yes/no question

# ------------------------------------------------------------------- judges
# A free local judge: install Ollama (https://ollama.com), then `ollama pull qwen3:8b`.
[judges.local]
type = "openai_compatible"
base_url = "http://localhost:11434/v1"
model = "qwen3:8b"
mode = "reason_then_verdict"
reasoning_effort = "none"            # qwen3 models think first; this is faster and avoids
                                     # replies cut off before the verdict
# For a hosted model: base_url = "https://api.openai.com/v1", model = "...",
# api_key_env = "OPENAI_API_KEY" (the key is read from the environment, never this file)

# -------------------------------------------------------------- evaluations
[evaluations.support]
dataset = "data/questions.jsonl"
criteria = { not_empty = "code", concise = "code", no_personal_data = "code" }
# Once a judge is running, add the LLM-judged checks:
# criteria = { not_empty = "code", concise = "code", no_personal_data = "code", correctness = "local", polite = "local" }

[runner]
max_concurrency = 4
max_cost_usd = 1.00
"""

APP = '''\
"""A tiny support bot to evaluate. Replace answer() with a call to your real app."""

ANSWERS = {
    "refund": "You can request a refund within 30 days of purchase.",
    "shipping": "We ship to the US and Canada; delivery takes 5-7 business days.",
    "password": "Use the 'Forgot password' link on the sign-in page to reset it.",
    "hours": "Our support team is available 9am-5pm, Monday to Friday.",
}


def answer(question: str) -> str:
    text = question.lower()
    for keyword, reply in ANSWERS.items():
        if keyword in text:
            return reply
    return "Sorry, I'm not sure. Please email support@example.com for help."
'''

QUESTIONS = """\
{"input": "What's your refund policy?", "reference": "Refunds within 30 days of purchase."}
{"input": "Can I get a refund after six weeks?", "reference": "No, refunds are only within 30 days."}
{"input": "Do you ship to Canada?", "reference": "Yes, to the US and Canada."}
{"input": "How long does shipping take?", "reference": "5-7 business days."}
{"input": "I forgot my password", "reference": "Use the Forgot password link on the sign-in page."}
{"input": "When is support open?", "reference": "9am-5pm, Monday to Friday."}
{"input": "Do you have a loyalty programme?", "reference": "No."}
{"input": "Can I change my delivery address?", "reference": "Yes, before the order ships."}
"""
