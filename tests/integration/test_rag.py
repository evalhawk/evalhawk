"""RAG end to end: a retrieval app, kind = "rag", retrieval metrics and contexts checks."""

import json
import os
import sys
from collections.abc import Iterator
from pathlib import Path

import pytest
from typer.testing import CliRunner

from evalhawk.cli._shared import console
from evalhawk.cli.main import app

runner = CliRunner()

APP = """
DOCS = {"refunds": "Refunds within 30 days.", "shipping": "We ship to the US and Canada.",
        "hours": "Support is open 9-5.", "password": "Reset it from the sign-in page."}

def answer(question):
    words = question.lower()
    ranked = sorted(DOCS, key=lambda doc: doc not in words)  # matching doc first
    top = ranked[:2]
    return {"output": DOCS[top[0]], "contexts": [DOCS[d] for d in top], "retrieved_ids": top}
"""

CONFIG = """
version = 1
[project]
store = ".evalhawk/eval.db"
[target]
type = "callable"
callable = "ragapp:answer"
[[criteria]]
name = "answered"
check = { type = "not_empty" }
[evaluations.docs]
dataset = "data.jsonl"
kind = "rag"
criteria = { answered = "code" }
"""

ROWS = [
    {"input": "What about refunds?", "relevant_ids": ["refunds"]},
    {"input": "Do you do shipping abroad?", "relevant_ids": ["shipping"]},
    {"input": "What are your hours?", "relevant_ids": ["hours"]},
    {"input": "Where do I change my login?", "relevant_ids": ["password"]},  # retriever misses
]


@pytest.fixture(autouse=True)
def wide_console(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(console, "width", 200)


@pytest.fixture
def project(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[Path]:
    # Each test writes its own ragapp.py; forget any copy imported by an earlier test.
    monkeypatch.delitem(sys.modules, "ragapp", raising=False)
    (tmp_path / "ragapp.py").write_text(APP, encoding="utf-8")
    (tmp_path / "evalhawk.toml").write_text(CONFIG, encoding="utf-8")
    (tmp_path / "data.jsonl").write_text(
        "\n".join(json.dumps(row) for row in ROWS) + "\n", encoding="utf-8"
    )
    previous = Path.cwd()
    os.chdir(tmp_path)
    yield tmp_path
    os.chdir(previous)


def test_rag_eval_then_retrieval_metrics(project: Path) -> None:
    result = runner.invoke(app, ["eval", "--target-version", "v1"])
    assert result.exit_code == 0, result.stdout
    metrics = runner.invoke(app, ["retrieval", "--run", "v1", "--k", "1", "--n-boot", "200"])
    assert metrics.exit_code == 0, metrics.stdout
    out = metrics.stdout
    assert "Retrieval quality (4 queries)" in out
    assert "hit@1" in out
    assert "0.750" in out  # 3 of 4 questions retrieve the right document first
    assert "MRR" in out


def test_rag_evaluation_requires_contexts(project: Path) -> None:
    (project / "ragapp.py").write_text(
        "def answer(question):\n    return 'no contexts here'\n", encoding="utf-8"
    )
    result = runner.invoke(app, ["eval", "--target-version", "v1"])
    assert result.exit_code == 0, result.stdout  # recorded as failures, not a crash
    assert "Failures" in result.stdout
    assert "returned no contexts" in result.stdout


def test_retrieval_explains_missing_ids(project: Path) -> None:
    (project / "data.jsonl").write_text(
        "\n".join(json.dumps({"input": row["input"]}) for row in ROWS) + "\n", encoding="utf-8"
    )
    assert runner.invoke(app, ["eval", "--target-version", "v1"]).exit_code == 0
    result = runner.invoke(app, ["retrieval", "--run", "v1"])
    assert result.exit_code == 1
    assert "add relevant_ids" in result.stdout
