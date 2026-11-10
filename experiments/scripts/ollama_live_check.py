"""End-to-end check with a real local judge (Ollama): judge, calibrate, correct, compare, gate.

    uv run python experiments/scripts/ollama_live_check.py --out <folder> [--model qwen3.5:4b]

What it does, in a fresh project folder:

1. Builds a support-bot dataset with a known answer for every question, and two recorded
   versions of the bot (v1 makes more mistakes than v2). Mistakes are unambiguous by
   construction: a wrong number, an invented feature, or "I'm not sure".
2. Runs ``evalhawk eval`` for both versions with the built-in ``correctness`` criterion,
   judged live by the Ollama model.
3. Adds **answer-key labels** (annotator ``answer-key``) to dev-pile answers only, standing
   in for a human labeller. Test-pile answers are never labelled.
4. Runs ``evalhawk report``, ``compare --corrected`` and ``gate``, then prints how the judge
   did against the answer key and the true pass rates the corrected numbers should match.

The truth is synthetic (we wrote the mistakes), but every verdict comes from the real model.
"""

import argparse
import json
import random
import sys
import time
from pathlib import Path

from typer.testing import CliRunner

from evalhawk.cli._shared import console
from evalhawk.cli.main import app
from evalhawk.core.models import Label, Outcome, Split
from evalhawk.core.splits import SplitSet
from evalhawk.services.calibrate import run_criteria
from evalhawk.storage.sqlite import SQLiteStore

# topic: (fact, (question phrasings...), (wrong answer, invented answer))
FACTS: dict[str, tuple[str, tuple[str, ...], tuple[str, str]]] = {
    "refund": (
        "Refunds are available within 30 days of purchase.",
        (
            "What's your refund policy?",
            "How long do I have to return something?",
            "Can I get my money back?",
            "What is the refund window?",
            "How many days do I have for a refund?",
            "Do you give refunds?",
        ),
        (
            "Refunds are available within 90 days of purchase.",
            "Refunds are available any time, no questions asked, plus a $10 credit.",
        ),
    ),
    "shipping_where": (
        "We ship to the US and Canada only.",
        (
            "Where do you ship?",
            "Do you ship to Canada?",
            "Which countries do you deliver to?",
            "Can you send orders to the US?",
            "Is shipping available in Canada?",
            "What are your shipping destinations?",
        ),
        (
            "We ship to the US, Canada, Mexico and the UK.",
            "We ship worldwide with free delivery to over 100 countries.",
        ),
    ),
    "shipping_time": (
        "Standard delivery takes 5-7 business days.",
        (
            "How long does shipping take?",
            "When will my order arrive?",
            "What's the delivery time?",
            "How many days until delivery?",
            "How fast is standard shipping?",
            "How long is delivery?",
        ),
        (
            "Standard delivery takes 1-2 business days.",
            "Delivery is same-day in every city we serve.",
        ),
    ),
    "express": (
        "Express delivery takes 2 business days and costs $15.",
        (
            "Do you have express shipping?",
            "How much is express delivery?",
            "Can I get my order faster?",
            "What does express shipping cost?",
            "Is there a quicker delivery option?",
            "How fast is express?",
        ),
        (
            "Express delivery takes 2 business days and costs $45.",
            "Express delivery is free and arrives within 3 hours.",
        ),
    ),
    "password": (
        "Reset your password with the Forgot password link on the sign-in page.",
        (
            "I forgot my password",
            "How do I reset my password?",
            "I can't log in",
            "My password doesn't work",
            "How can I change my password?",
            "I'm locked out of my account",
        ),
        (
            "Call our phone line and an agent will read your password to you.",
            "Passwords reset automatically every 24 hours, so just wait a day.",
        ),
    ),
    "hours": (
        "Support is open 9am-5pm, Monday to Friday.",
        (
            "When is support open?",
            "What are your support hours?",
            "Can I contact support on Saturday?",
            "Is support available at night?",
            "What time does support close?",
            "When can I reach an agent?",
        ),
        (
            "Support is open 24 hours a day, 7 days a week.",
            "Support is open 9am-5pm every day including weekends and holidays.",
        ),
    ),
    "warranty": (
        "All products have a 1-year warranty.",
        (
            "Do your products have a warranty?",
            "How long is the warranty?",
            "What does the warranty cover?",
            "Is there a guarantee?",
            "How many years of warranty do I get?",
            "Can I claim warranty after a year?",
        ),
        (
            "All products have a 5-year warranty.",
            "All products have a lifetime warranty with free replacements.",
        ),
    ),
    "cancel": (
        "You can cancel an order until it ships.",
        (
            "Can I cancel my order?",
            "How do I cancel?",
            "Is it too late to cancel?",
            "Can I cancel after it has shipped?",
            "What's the cancellation policy?",
            "I want to cancel my purchase",
        ),
        (
            "Orders can be cancelled up to 60 days after delivery.",
            "Orders cannot be cancelled under any circumstances.",
        ),
    ),
    "gift_cards": (
        "Gift cards are non-refundable.",
        (
            "Can I refund a gift card?",
            "Are gift cards refundable?",
            "I want my money back for a gift card",
            "Can gift cards be returned?",
            "What happens if I don't use my gift card?",
            "Do gift cards expire or refund?",
        ),
        (
            "Gift cards can be refunded within 30 days.",
            "Gift cards can be exchanged for cash at any store.",
        ),
    ),
    "student": (
        "Students get a 10% discount with a valid student email.",
        (
            "Do you have a student discount?",
            "How much is the student discount?",
            "Are there discounts for students?",
            "Can students save money?",
            "What do I need for the student discount?",
            "Is there an education discount?",
        ),
        (
            "Students get a 50% discount with a valid student email.",
            "Students get free products every month with a student email.",
        ),
    ),
    "loyalty": (
        "We do not have a loyalty programme.",
        (
            "Do you have a loyalty programme?",
            "Do I earn points?",
            "Is there a rewards scheme?",
            "Can I collect loyalty points?",
            "Do you have a membership club?",
            "Are there rewards for frequent buyers?",
        ),
        (
            "Yes, you earn 5 points for every dollar you spend.",
            "Yes, our Gold Club gives members double points and free shipping.",
        ),
    ),
    "price_match": (
        "We do not offer price matching.",
        (
            "Do you price match?",
            "Will you match a competitor's price?",
            "Can I get the lower price from another shop?",
            "Do you have a price guarantee?",
            "Will you beat other prices?",
            "Is there price matching?",
        ),
        (
            "Yes, we match any competitor's price within 14 days.",
            "Yes, we beat any competitor's price by 20%.",
        ),
    ),
    "address": (
        "You can change the delivery address until the order ships.",
        (
            "Can I change my delivery address?",
            "I entered the wrong address",
            "How do I update my shipping address?",
            "Can I ship to a different address?",
            "My address is wrong on the order",
            "Can I edit the address after ordering?",
        ),
        (
            "You can change the address up to 10 days after delivery.",
            "Addresses can only be changed by mailing a signed letter.",
        ),
    ),
    "payment": (
        "We accept Visa, Mastercard and PayPal.",
        (
            "What payment methods do you accept?",
            "Can I pay with PayPal?",
            "Do you take Mastercard?",
            "How can I pay?",
            "Do you accept credit cards?",
            "Which cards can I use?",
        ),
        (
            "We accept Visa, Mastercard, PayPal, Bitcoin and bank cheques.",
            "We only accept cash on delivery.",
        ),
    ),
}
UNSURE = "Sorry, I'm not sure. Please email support@example.com for help."
# chance of each answer kind per version: (correct, wrong number/fact, invented, unsure)
MIX = {"v1": (0.55, 0.15, 0.15, 0.15), "v2": (0.75, 0.08, 0.07, 0.10)}

CONFIG = """\
version = 1

[project]
name = "ollama-live-check"
store = ".evalhawk/eval.db"

[target]
type = "recorded"

[splits]
salt = "ollama-live"
by = "example_id"

[[criteria]]
name = "correctness"
template = "correctness"

[judges.local]
type = "openai_compatible"
base_url = "{base_url}"
model = "{model}"
mode = "reason_then_verdict"
reasoning_effort = "none"
max_tokens = 400
timeout = 180

# The cheap half of a cascade: same model, one word, P(PASS) from logprobs.
[judges.quick]
type = "openai_compatible"
base_url = "{base_url}"
model = "{model}"
mode = "verdict_only"
reasoning_effort = "none"
timeout = 180

[evaluations.v1]
dataset = "data/v1.jsonl"
criteria = {{ correctness = ["local", "quick"] }}

[evaluations.v2]
dataset = "data/v2.jsonl"
criteria = {{ correctness = ["local", "quick"] }}

[runner]
max_concurrency = 2
retries = 2
"""


def build(folder: Path, seed: int) -> dict[tuple[str, str], bool]:
    """Write the two recorded datasets; return the answer key (version, input) -> correct."""
    rng = random.Random(seed)
    key: dict[tuple[str, str], bool] = {}
    (folder / "data").mkdir(parents=True, exist_ok=True)
    rows: dict[str, list[dict[str, str]]] = {"v1": [], "v2": []}
    for fact, questions, (wrong, invented) in FACTS.values():
        for question in questions:
            draw = rng.random()
            for version, mix in MIX.items():
                if draw < mix[0]:
                    answer, correct = fact, True
                elif draw < mix[0] + mix[1]:
                    answer, correct = wrong, False
                elif draw < mix[0] + mix[1] + mix[2]:
                    answer, correct = invented, False
                else:
                    answer, correct = UNSURE, False
                rows[version].append({"input": question, "reference": fact, "output": answer})
                key[(version, question)] = correct
    for version, items in rows.items():
        with (folder / "data" / f"{version}.jsonl").open("w", encoding="utf-8") as out:
            out.writelines(json.dumps(row) + "\n" for row in items)
    return key


def cli(*args: str) -> str:
    result = CliRunner().invoke(app, list(args))
    print(result.stdout)
    if result.exit_code not in (0, 1):
        sys.exit(f"evalhawk {' '.join(args)} failed with exit code {result.exit_code}")
    return result.stdout


def main() -> None:
    parser = argparse.ArgumentParser(description="End-to-end check with a real Ollama judge.")
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--model", default="qwen3.5:4b")
    parser.add_argument("--base-url", default="http://localhost:11434/v1")
    parser.add_argument("--seed", type=int, default=7)
    args = parser.parse_args()
    console.width = 130
    folder: Path = args.out.resolve()
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "evalhawk.toml").write_text(
        CONFIG.format(base_url=args.base_url, model=args.model), encoding="utf-8"
    )
    key = build(folder, args.seed)
    db = folder / ".evalhawk" / "eval.db"
    config = str(folder / "evalhawk.toml")

    started = time.perf_counter()
    for version in ("v1", "v2"):
        cli("eval", "-t", version, "--evaluation", version, "--config", config)
    print(f"Judging took {time.perf_counter() - started:.0f}s")

    # Answer-key labels on the dev pile only (a stand-in for a human labeller).
    store = SQLiteStore(db)
    agreement = {Split.DEV: [0, 0], Split.TEST: [0, 0]}
    try:
        for run in store.list_runs():
            splits = SplitSet.model_validate(run.config_snapshot["splits"])
            entry = next(e for e in run_criteria(run) if e["judge"] == "local")
            for trace in store.iter_traces(run.id):
                example = store.get_example(trace.example_id)
                assert example is not None
                truth = key[(run.target_version, str(example.input))]
                pile = store.get_split(splits.id, example.id)
                verdict = store.get_verdict(trace.id, entry["criterion_id"], entry["judge_id"])
                if verdict is not None and pile is not None and pile in agreement:
                    agreement[pile][0] += (verdict.outcome is Outcome.PASS) == truth
                    agreement[pile][1] += 1
                if pile is Split.DEV:
                    store.add_label(
                        Label(
                            trace_id=trace.id,
                            criterion_id=entry["criterion_id"],
                            annotator="answer-key",
                            outcome=Outcome.PASS if truth else Outcome.FAIL,
                        )
                    )
    finally:
        store.close()

    for version in ("v1", "v2"):
        for judge in ("local", "quick"):
            cli(
                "report",
                "--run",
                version,
                "--db",
                str(db),
                "--criterion",
                "correctness",
                "--judge",
                judge,
            )
    pick = ("--criterion", "correctness", "--judge", "local")
    cli("compare", "--baseline", "v1", "--candidate", "v2", "--db", str(db), *pick)
    cli("compare", "--baseline", "v1", "--candidate", "v2", "--db", str(db), *pick, "--corrected")
    cli(
        "judges",
        "cascade",
        "--run",
        "v1",
        "--criterion",
        "correctness",
        "--cheap",
        "quick",
        "--strong",
        "local",
        "--config",
        config,
    )
    gate = CliRunner().invoke(
        app,
        ["gate", "--baseline", "v1", "--candidate", "v2", "--db", str(db), *pick, "--corrected"],
    )
    print(gate.stdout)
    print(f"Gate exit code: {gate.exit_code} (0 = OK, 1 = significant regression)")

    print("Judge agreement with the answer key (every judged answer):")
    for pile, (right, total) in agreement.items():
        print(f"  {pile.value}: {right}/{total} = {right / total:.1%}" if total else f"  {pile}: -")
    for version in ("v1", "v2"):
        truths = [ok for (v, _), ok in key.items() if v == version]
        print(f"True pass rate {version} (all questions): {sum(truths) / len(truths):.1%}")


if __name__ == "__main__":
    main()
