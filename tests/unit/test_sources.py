import tracemalloc
from pathlib import Path

import pytest

from evalhawk.core.errors import DataError
from evalhawk.sources.csv import CSVSource
from evalhawk.sources.jsonl import JSONLSource


def test_jsonl_streams_normalized_rows_and_metadata(tmp_path: Path) -> None:
    path = tmp_path / "answers.jsonl"
    path.write_text(
        '\n{"input":"Cafe\\u0301","output":"answer","group_id":17,"tags":["billing"],"custom":true}\n{"input":"second"}\n',
        encoding="utf-8",
    )
    iterator = iter(JSONLSource(path).load())
    example, output = next(iterator)
    assert example.input == "Caf\u00e9"
    assert example.group_id == "17"
    assert example.metadata == {"custom": True}
    assert output is not None
    assert output.output == "answer"
    assert next(iterator)[1] is None


def test_csv_handles_bom_json_contexts_and_multi_tags(tmp_path: Path) -> None:
    path = tmp_path / "answers.csv"
    path.write_text(
        'input,output,tags,contexts\nquestion,answer,billing|refund,"[""source""]"\n',
        encoding="utf-8-sig",
    )
    example, output = next(iter(CSVSource(path).load()))
    assert example.tags == ("billing", "refund")
    assert output is not None
    assert output.contexts == ("source",)


@pytest.mark.parametrize(
    ("source", "suffix", "contents"),
    [
        (JSONLSource, ".jsonl", '{"output":"answer"}\n'),
        (CSVSource, ".csv", "input,output\n,answer\n"),
    ],
)
def test_bad_row_names_file_row_field(
    tmp_path: Path, source: type[JSONLSource] | type[CSVSource], suffix: str, contents: str
) -> None:
    path = tmp_path / ("bad" + suffix)
    path.write_text(contents, encoding="utf-8")
    with pytest.raises(DataError, match=r"bad.*row.*input"):
        list(source(path).load())


@pytest.mark.slow
@pytest.mark.parametrize("source", [JSONLSource, CSVSource])
def test_large_import_has_bounded_memory(
    tmp_path: Path, source: type[JSONLSource] | type[CSVSource]
) -> None:
    path = tmp_path / "large.txt"
    with path.open("w", encoding="utf-8") as stream:
        if source is CSVSource:
            stream.write("input,output\n")
        for index in range(100_000):
            stream.write(
                f'{{"input":"question {index}","output":"answer"}}\n'
                if source is JSONLSource
                else f"question {index},answer\n"
            )
    tracemalloc.start()
    try:
        assert sum(1 for _ in source(path).load()) == 100_000
        _, peak = tracemalloc.get_traced_memory()
        assert peak < 8_000_000
    finally:
        tracemalloc.stop()
