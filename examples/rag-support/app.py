"""A toy retrieval-augmented support bot. Replace answer() with your real RAG pipeline."""

DOCS = {
    "refunds": "Refunds are available within 30 days of purchase, to the original card.",
    "shipping": "We ship to the US and Canada. Delivery takes 5-7 business days.",
    "passwords": "Reset a password with the Forgot password link on the sign-in page.",
    "hours": "Support is open 9am-5pm, Monday to Friday.",
    "address": "You can change the delivery address until the order ships.",
}
KEYWORDS = {
    "refunds": ("refund", "money back"),
    "shipping": ("ship", "delivery", "deliver"),
    "passwords": ("password", "log in", "sign in"),
    "hours": ("open", "hours", "when"),
    "address": ("address",),
}


def retrieve(question: str, k: int = 2) -> list[str]:
    """Rank documents by how many of their keywords appear in the question."""
    text = question.lower()
    scores = {doc: sum(word in text for word in words) for doc, words in KEYWORDS.items()}
    ranked = sorted((doc for doc, score in scores.items() if score), key=lambda d: -scores[d])
    return ranked[:k]


def answer(question: str) -> dict[str, object]:
    """Return the answer plus what was retrieved, so EvalHawk can score retrieval too."""
    ids = retrieve(question)
    contexts = [DOCS[i] for i in ids]
    if contexts:
        output = contexts[0]
    elif "loyalty" in question.lower():  # a deliberate bug: the bot makes something up
        output = "Yes! Our loyalty programme gives you 5 points per dollar spent."
    else:
        output = "Sorry, I don't know. Please contact support."
    return {"output": output, "contexts": contexts, "retrieved_ids": ids}
