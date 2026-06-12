# ai-readiness-audit

Diagnoses how well a website can be read by AI crawlers (ChatGPT, Gemini, Perplexity, etc.).
A CLI tool powering the "AI Readiness Audit" consulting service.

**Report quality = product quality.**

---

## Quick start

```bash
uv run ai-audit run https://example.com
```

Outputs on every run (auto-saved to `results/{domain}/{timestamp}/`):
- `report.pdf` — 3-page A4 professional report
- `report_web.html` — interactive report (accordion + tabs)
- `result.json` — machine-readable raw data for trend tracking

Manual export:
```bash
uv run ai-audit run https://example.com --out report.pdf
uv run ai-audit run https://example.com --out report_web.html
```

---

## Install

```bash
git clone https://github.com/zackguo-dev/ai-readiness-audit
cd ai-readiness-audit
uv sync
uv run playwright install chromium
```

**Requirements:** Python 3.12+ / uv

**PDF export (WeasyPrint):** Requires GTK3 runtime on Windows.
Download installer: https://github.com/tschoonj/GTK-for-Windows-Runtime-Environment-Installer/releases

---

## Output formats

| Format | Use case | Auto-saved |
|---|---|---|
| PDF (3-page A4) | Client delivery, printing | ✓ |
| Interactive HTML | Browser review, internal sharing | ✓ |
| JSON | Trend tracking, before/after comparison | ✓ |

---

## Diagnosis checks (v1)

| # | Check | Description | Weight |
|---|---|---|---|
| 1 | bot_access | Access status for 8 major AI crawlers via robots.txt + live HEAD requests | High |
| 2 | llms_txt | Presence and format validity of llms.txt / llms-full.txt | Low |
| 3 | js_dependency | Static HTML vs Playwright-rendered text volume comparison | **Highest** |
| 4 | structured_data | JSON-LD (Schema.org) implementation and missing required properties | High |
| 5 | semantic_html | Heading hierarchy, alt attributes, meta description, OGP | Medium |
| 6 | freshness | Date markup and sitemap.xml presence | Medium |

**Monitored AI crawlers (bot_access):**
GPTBot / ClaudeBot / Claude-Web / PerplexityBot / Google-Extended / CCBot / Bytespider / meta-externalagent

---

## Report structure

### PDF (3 pages)

- **Page 1 — Summary:** Total score, critical/warning/good counts, score bar for all 6 checks
- **Page 2 — Detail:** Findings per check (what was found and why it matters)
- **Page 3 — Action roadmap:** Prioritized improvement actions (high / medium / low), each labeled "自社で対応可" or "Webサイトの制作会社へ依頼"

### Interactive HTML

- Tab 1 (サマリー): Click-to-expand accordion rows — each check shows score bar + findings + recommendations
- Tab 2 (詳細): Full action list with priority badges and cost estimates

---

## Project structure

```
ai_audit/
  cli.py                  # typer entry point
  target.py               # TargetSite: fetch once, reuse across all checks
  checks/
    bot_access.py
    llms_txt.py
    js_dependency.py
    structured_data.py
    semantic_html.py
    freshness.py
  report/
    renderer.py            # render_html() → PDF, render_web_html() → interactive
    templates/
      report.html.j2       # static template for PDF (WeasyPrint)
      report_web.html.j2   # interactive template for browser
results/                   # auto-saved outputs (gitignored)
docs/
  SERVICE_SPEC.md          # technical spec for partners and clients
  USER_GUIDE.md            # how to read the report (for non-technical clients)
tests/
  fixtures/                # HTML fixtures for offline testing
.claude/agents/            # sub-agent definitions for Claude Code
CLAUDE.md                  # project constitution
```

---

## Architecture

### TargetSite

Fetches all required resources once (HTML, robots.txt, llms.txt, llms-full.txt) with 1-second intervals between requests. All checks read from this cached object — no check fetches independently.

Exception: `bot_access` sends UA-specific HEAD requests (1-second intervals, 8 bots).

### CheckResult

```python
@dataclass
class CheckResult:
    score: int                    # 0–100
    findings: list[str]           # issues found (Japanese)
    recommendations: list[dict]   # {text, type: "self"|"professional", cost, priority}
```

### ReportData (renderer input)

Key computed fields (all calculated in `renderer.py`, not in templates):

```python
score_color: str          # hex based on score tier
donut_offset: float       # SVG stroke-dashoffset for donut chart
count_critical: int       # checks with score < 40
count_warning: int        # checks with score 40–69
count_good: int           # checks with score >= 70
actions_high: list        # professional actions from checks < 40
actions_mid: list         # professional actions 40–69 + all self-service actions
actions_low: list         # llms.txt and low-priority items
```

---

## Agent structure (Claude Code)

| Agent | Role | When to use |
|---|---|---|
| check-builder | Implement check modules | Any change to `checks/` |
| test-guardian | Write and run tests | After every implementation (mandatory) |
| report-craftsman | Report copy and templates | Any change to Japanese output or templates |
| scope-keeper | Scope guard + session management | Start, end, and any scope-creep moment |

---

## Testing

```bash
python -m pytest                    # all tests (208 passing)
python -m pytest tests/test_bot.py  # specific module
python -m pytest -v                 # verbose
```

Note: Use `python -m pytest` instead of `uv run pytest` (uv trampoline issue on this machine, no functional impact).

Playwright-dependent tests skip gracefully when GTK3 is not installed.

---

## Versioning

| Version | Status | Content |
|---|---|---|
| v1 (current) | Complete | 6 checks, PDF (3-page), interactive HTML, JSON log |
| v2 (planned) | — | AI mention monitoring via LLM API (separate repo) |

Items explicitly out of scope for v1: SEO ranking, content quality scoring, GUI, SaaS.

---

## Ethics and usage

- Always obtain permission before diagnosing a site you don't own
- Never claim "your site will definitely be cited by AI" — the report never makes this guarantee
- llms.txt effectiveness is currently limited; the report states this honestly
- Score color rules: 0–39 red (critical), 40–69 amber (warning), 70–100 green (good)

---

## Development log

| Date | Commit | Change |
|---|---|---|
| 2026-06-12 | 64b765b | v1 complete: 6 checks, JSON + MD output, tests passing |
| 2026-06-12 | d77ab13 | Static HTML report template |
| 2026-06-12 | 04b54af | PDF export via WeasyPrint |
| 2026-06-12 | 662a7da | PDF page-break and layout fix |
| 2026-06-13 | 4e80138 | Interactive web HTML report (accordion + tabs) |
| 2026-06-13 | f847462 | 3-page PDF redesign (brand header, summary grid, action roadmap) |

---

[CC BY-NC 4.0](https://creativecommons.org/licenses/by-nc/4.0/deed.ja)

個人学習目的の閲覧・利用は自由。サービスとしての再販・商用利用は禁止。
