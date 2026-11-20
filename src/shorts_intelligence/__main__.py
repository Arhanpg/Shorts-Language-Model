"""Minimal CLI placeholder until the Phase 1 analyzer is implemented."""

import typer
from rich import print

app = typer.Typer(help="Short-form video intelligence research tools.")


@app.command()
def status() -> None:
    """Show the initial repository status."""
    print("[bold green]Shorts Language Model foundation is installed.[/bold green]")
    print("Next: implement the rights-aware single-video telemetry pipeline.")


if __name__ == "__main__":
    app()
