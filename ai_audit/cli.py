"""typer エントリポイント — `ai-audit run <URL>`。"""

from __future__ import annotations

from pathlib import Path
from typing import Optional

import typer

from .checks import CHECKS
from .report import render_report
from .target import TargetSite

app = typer.Typer(
    help="WebサイトがAIクローラーにどれだけ読めるかを診断するCLI。",
    no_args_is_help=True,
    add_completion=False,
)


@app.callback()
def _main() -> None:
    """サブコマンド名(run)を保持するためのコールバック。"""


@app.command()
def run(
    url: str = typer.Argument(..., help="診断対象のURL（例: https://example.com）"),
    out: Optional[Path] = typer.Option(
        None, "--out", "-o", help="レポートの出力先(.md)。未指定なら標準出力。"
    ),
) -> None:
    """対象サイトを診断し、日本語Markdownレポートを出力する。"""
    typer.echo(f"診断中: {url} ...", err=True)
    target = TargetSite.fetch(url)

    if target.status == 0:
        typer.echo(
            f"ページを取得できませんでした: {url}\n" + "\n".join(target.errors),
            err=True,
        )
        raise typer.Exit(code=1)

    results = [module.run(target) for module in CHECKS]
    weights = {module.CHECK_ID: module.WEIGHT for module in CHECKS}
    report = render_report(url, results, weights, fetched_at=target.fetched_at)

    if out:
        out.write_text(report, encoding="utf-8")
        typer.echo(f"レポートを書き出しました: {out}", err=True)
    else:
        typer.echo(report)


if __name__ == "__main__":
    app()
