"""Entry point for the ``evalhawk`` command."""

from typing import Annotated

import typer

from evalhawk import __version__

app = typer.Typer(
    name="evalhawk",
    help="Trustworthy LLM evaluation: calibrate judges, get honest numbers.",
    no_args_is_help=True,
    add_completion=False,
)


def _version_callback(value: bool) -> None:
    if value:
        typer.echo(f"evalhawk {__version__}")
        raise typer.Exit()


@app.callback()
def main(
    version: Annotated[
        bool,
        typer.Option(
            "--version",
            "-V",
            callback=_version_callback,
            is_eager=True,
            help="Show the version and exit.",
        ),
    ] = False,
) -> None:
    """Calibrate LLM judges against humans and report bias-corrected results."""
