"""TF-IDF + k-means over short texts, in NumPy (no scikit-learn, no embedding model).

Good enough to surface recurring failure reasons ("wrong refund window", "invents a
loyalty programme") from a few hundred notes; it is a discovery aid for a human, who
decides which clusters become criteria.

* **TF-IDF**: each text becomes a vector of word weights; words common across all texts
  (like "the" or "answer") get low weight, distinctive words get high weight.
* **k-means++**: groups vectors around ``k`` centres; seeded, so results are reproducible.
"""

import math
import re
from collections import Counter
from dataclasses import dataclass

import numpy as np
import numpy.typing as npt

_WORD = re.compile(r"[a-z][a-z0-9']+")
STOPWORDS = frozenset(
    [
        "a",
        "an",
        "and",
        "are",
        "as",
        "at",
        "be",
        "but",
        "by",
        "for",
        "from",
        "has",
        "have",
        "i",
        "if",
        "in",
        "into",
        "is",
        "it",
        "its",
        "of",
        "on",
        "or",
        "so",
        "that",
        "the",
        "their",
        "there",
        "this",
        "to",
        "was",
        "were",
        "will",
        "with",
        "not",
        "no",
        "yes",
        "does",
        "do",
        "did",
        "should",
        "would",
        "could",
        "can",
        "answer",
        "answers",
        "response",
        "model",
        "judge",
        "verdict",
        "pass",
        "fail",
        "unknown",
        "claim",
        "claims",
        "user",
        "question",
    ]
)


@dataclass(frozen=True, slots=True)
class Cluster:
    """One group of similar texts: its size, defining words and representative texts."""

    size: int
    top_terms: tuple[str, ...]
    examples: tuple[str, ...]
    members: tuple[int, ...]


def _tokens(text: str) -> list[str]:
    return [word for word in _WORD.findall(text.lower()) if word not in STOPWORDS]


def tfidf(
    texts: list[str], *, max_features: int = 2000, min_df: int = 1
) -> tuple[npt.NDArray[np.float64], list[str]]:
    """L2-normalised TF-IDF matrix (texts x vocabulary) and the vocabulary."""
    docs = [_tokens(text) for text in texts]
    df: Counter[str] = Counter(word for doc in docs for word in set(doc))
    vocab = [w for w, c in sorted(df.items(), key=lambda item: (-item[1], item[0])) if c >= min_df]
    vocab = vocab[:max_features]
    index = {word: i for i, word in enumerate(vocab)}
    matrix = np.zeros((len(texts), len(vocab)))
    for row, doc in enumerate(docs):
        for word, count in Counter(doc).items():
            if word in index:
                matrix[row, index[word]] = count
    idf = np.log((1 + len(texts)) / (1 + np.array([df[w] for w in vocab], dtype=float))) + 1
    matrix *= idf
    norms = np.linalg.norm(matrix, axis=1, keepdims=True)
    return np.divide(matrix, norms, out=np.zeros_like(matrix), where=norms > 0), vocab


def kmeans(
    points: npt.NDArray[np.float64], k: int, *, rng: np.random.Generator, iterations: int = 100
) -> npt.NDArray[np.int64]:
    """Cluster labels from k-means++ initialisation and Lloyd iterations."""
    n = points.shape[0]
    k = max(1, min(k, n))
    centres = [points[rng.integers(n)]]
    for _ in range(1, k):
        distance = np.min([((points - c) ** 2).sum(axis=1) for c in centres], axis=0)
        total = distance.sum()
        choice = rng.choice(n, p=distance / total) if total > 0 else rng.integers(n)
        centres.append(points[choice])
    centre_matrix = np.array(centres)
    labels = np.zeros(n, dtype=np.int64)
    for _ in range(iterations):
        distances = ((points[:, None, :] - centre_matrix[None, :, :]) ** 2).sum(axis=2)
        new_labels = distances.argmin(axis=1)
        if np.array_equal(new_labels, labels) and _ > 0:
            break
        labels = new_labels
        for j in range(k):
            members = points[labels == j]
            if len(members):
                centre_matrix[j] = members.mean(axis=0)
    return labels


def cluster_texts(
    texts: list[str],
    *,
    k: int | None = None,
    rng: np.random.Generator,
    top_terms: int = 5,
    examples: int = 3,
) -> list[Cluster]:
    """Group texts into clusters, largest first. ``k`` defaults to about sqrt(n / 2)."""
    if not texts:
        raise ValueError("no texts to cluster")
    matrix, vocab = tfidf(texts)
    if not vocab:
        raise ValueError("the texts have no informative words to cluster on")
    k = k or max(1, round(math.sqrt(len(texts) / 2)))
    labels = kmeans(matrix, k, rng=rng)
    clusters: list[Cluster] = []
    for label in np.unique(labels):
        members = np.flatnonzero(labels == label)
        centre = matrix[members].mean(axis=0)
        terms = tuple(vocab[i] for i in np.argsort(-centre)[:top_terms] if centre[i] > 0)
        closest = members[np.argsort(-(matrix[members] @ centre))][:examples]
        clusters.append(
            Cluster(
                size=int(members.size),
                top_terms=terms,
                examples=tuple(texts[i] for i in closest),
                members=tuple(int(i) for i in members),
            )
        )
    return sorted(clusters, key=lambda c: (-c.size, c.top_terms))
