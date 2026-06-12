"""typer エントリポイント — `ai-audit run <URL>`。"""

from __future__ import annotations

from pathlib import Path

import typer

from .checks import CHECKS
from .report import build_report_data, render_html, render_pdf, render_web_html
from .report.json_writer import save_results_json
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
    out: Path = typer.Option(
        Path("report.html"), "--out", "-o", help="レポートの出力先(.html または .pdf)。"
    ),
) -> None:
    """対象サイトを診断し、日本語HTMLレポートを出力する。"""
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

    report_data = build_report_data(
        target.final_url, results, weights, fetched_at=target.fetched_at
    )
    html = render_html(report_data)

    # results/{domain}/{timestamp}.json と同階層に .html も保存
    json_path = save_results_json(url, target.final_url, target.fetched_at, results, weights)
    typer.echo(f"JSON保存: {json_path}", err=True)

    # web HTML（インタラクティブ）を自動保存
    web_html = render_web_html(report_data)
    web_html_path = json_path.with_name(json_path.stem + "_web.html")
    web_html_path.write_text(web_html, encoding="utf-8")
    typer.echo(f"WebHTML保存: {web_html_path}", err=True)

    html_path = json_path.with_suffix(".html")
    html_path.write_text(html, encoding="utf-8")
    typer.echo(f"HTML保存: {html_path}", err=True)

    # PDF も自動保存
    try:
        pdf_bytes = render_pdf(html)
        pdf_path = json_path.with_suffix(".pdf")
        pdf_path.write_bytes(pdf_bytes)
        typer.echo(f"PDF保存: {pdf_path}", err=True)
    except ImportError as exc:
        typer.echo(f"PDF保存スキップ: {exc}", err=True)

    if out.suffix.lower() == ".pdf":
        try:
            out.write_bytes(render_pdf(html))
        except ImportError as exc:
            typer.echo(f"エラー: {exc}", err=True)
            raise typer.Exit(code=1)
    elif out.name.endswith("_web.html") or out.name == "report_web.html":
        out.write_text(web_html, encoding="utf-8")
    else:
        out.write_text(html, encoding="utf-8")
    typer.echo(f"レポートを書き出しました: {out}", err=True)


if __name__ == "__main__":
    app()
