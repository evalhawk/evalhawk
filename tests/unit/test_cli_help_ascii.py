"""Help text must print on legacy Windows consoles (cp1252), so CLI sources stay ASCII."""

from pathlib import Path

import evalhawk.cli


def test_cli_sources_are_ascii() -> None:
    folder = Path(evalhawk.cli.__file__).parent
    offenders = [
        f"{path.name}:{number}"
        for path in sorted(folder.glob("*.py"))
        for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1)
        if not line.isascii()
    ]
    assert offenders == [], f"non-ASCII text breaks `--help` on cp1252 consoles: {offenders}"
