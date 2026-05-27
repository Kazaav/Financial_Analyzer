# Financial Analyzer

**[English]** | [日本語](README.ja.md)

> Extract, compare, and visualise financial data from Japanese 有価証券報告書 (annual securities report) PDFs.

A small web tool that reads consolidated financials directly out of EDINET-style PDF reports and turns them into a clean, comparable dashboard. Built originally to speed up my own document-by-document analysis when reading dozens of reports for graduate research — published so anyone facing the same paperwork can avoid the same grind.

GitHub: **<https://github.com/Kazaav/Financial_Analyzer>**  
Live: **<https://fin.zekkx.icu>**

---

## Features

- **Structural PDF parsing** — locates 主要な経営指標等の推移, 連結貸借対照表/連結財政状態計算書, 連結損益計算書, and 連結キャッシュ・フロー計算書 sections page-by-page. Handles JGAAP and IFRS reports with synonym resolution (売上高 ⇆ 売上収益, 親会社株主に帰属する当期純利益 ⇆ 親会社の所有者に帰属する当期利益, 純資産 ⇆ 資本合計, etc.).
- **13 raw + 12 derived metrics** — sales, profit, assets, cash flows extracted directly from the PDF; ROA, ROE, equity ratio, margins, growth rates etc. computed with the formulas shown alongside the values.
- **Three analysis modes**
  - **多社同年度** — cross-section of multiple companies in one fiscal year
  - **同一企業時系列** — time-series of one company across years
  - **カスタム** — pick any subset of PDFs and compare freely
- **Source traceability** — every extracted number carries a page badge linking back to the original PDF page rendered inline.
- **Interactive charts** — ECharts dark theme; line / bar / scatter automatically chosen per mode.
- **Exports** — CSV (UTF-8 BOM, opens cleanly in Excel), Excel (3-sheet, with metric source trace), JSON (full structured payload), standalone HTML report, browser-print PDF.
- **Trilingual UI** — Japanese / English / Chinese (financial terminology stays Japanese because the source documents are).
- **Public demos** — three pre-loaded sample analyses on the landing page; no login required.

---

## Tech stack

- **Backend**: Python 3.11+, FastAPI, uvicorn
- **PDF parsing**: PyMuPDF (fitz)
- **Charts**: ECharts 5 (CDN)
- **Excel export**: openpyxl
- **Templating**: Jinja2
- **Frontend**: vanilla HTML/CSS/JS — no build step
- **Observability**: prometheus_client, JSON-line logs
- **Reverse proxy (prod)**: Caddy with automatic HTTPS
- **Process management**: systemd

No JavaScript framework, no bundler, no Docker required. The whole app starts with one `uvicorn` command.

---

## Architecture

```
┌────────────────────────────────────────────────────────────────┐
│                          Browser                                │
│  Landing · Demos · Analysis dashboard · ECharts · Source modal  │
└──────────────────────────────┬─────────────────────────────────┘
                               │ HTTPS
                       ┌───────▼────────┐
                       │     Caddy      │   (automatic TLS, gzip/zstd)
                       └───────┬────────┘
                               │ HTTP 127.0.0.1:8010
                  ┌────────────▼────────────┐
                  │      FastAPI app        │
                  │  ┌──────────────────┐   │
                  │  │ auth + i18n + cleanup middleware │
                  │  │ metrics middleware │
                  │  └────────┬─────────┘   │
                  │           │             │
                  │  ┌────────▼─────────┐   │
                  │  │ pdf_parser.py    │   │  PyMuPDF text extraction,
                  │  │ analysis.py      │   │  synonym resolution,
                  │  │ export.py        │   │  derived metric calc,
                  │  │ reporting.py     │   │  CSV/XLSX/JSON export
                  │  └────────┬─────────┘   │
                  │           │             │
                  │  ┌────────▼─────────┐   │
                  │  │  storage (JSON)   │  │  /var/lib/financial-analyzer/
                  │  └──────────────────┘   │
                  └─────────────────────────┘
```

Storage is plain JSON files on disk — fine for the personal-tool use case, and trivial to back up.

---

## Quick start

### Prerequisites
- Python 3.11 or newer
- About 100MB free for the venv + dependencies

### Local run

```bash
git clone https://github.com/Kazaav/Financial_Analyzer.git
cd financial-analyzer
python -m venv venv
source venv/bin/activate      # Windows: venv\Scripts\activate
pip install -e ".[dev]"

# Optional: point storage somewhere other than ./storage/
export FINANCIAL_ANALYZER_STORAGE=/tmp/fa-storage

# Optional: replace the default user (admin / guest001)
#   format: username:role:pbkdf2_sha256$iterations$salt$hash
# export FINANCIAL_ANALYZER_USERS="me:admin:pbkdf2_sha256$..."

uvicorn app.main:app --reload --port 8010
```

Open <http://localhost:8010>. Default credentials: `admin` / `guest001`.

### Run tests

```bash
pytest                              # all tests
pytest tests/test_pdf_parser.py     # parser unit tests only
ruff check .                        # lint
mypy app                            # type check (non-strict)
```

---

## Configuration

| Env var | Default | Purpose |
| --- | --- | --- |
| `FINANCIAL_ANALYZER_STORAGE` | `./storage` | Where analysis JSONs, uploads, reports live |
| `FINANCIAL_ANALYZER_USERS` | `admin:admin:pbkdf2_sha256$...` | Semicolon-separated `username:role:hash` entries |
| `FINANCIAL_ANALYZER_SESSION_SECRET` | random per-process | HMAC secret for session cookies (set in prod) |
| `FINANCIAL_ANALYZER_SESSION_MAX_AGE_SECONDS` | 43200 (12h) | Login persistence |
| `FINANCIAL_ANALYZER_COOKIE_SECURE` | `0` | Set `1` behind HTTPS so cookies are HTTPS-only |
| `FINANCIAL_ANALYZER_RETENTION_DAYS` | `7` | How long user uploads / reports are kept; set `0` to disable cleanup |

Demo records (any analysis ID prefixed `demo-`) are exempt from cleanup.

To hash a new password:

```python
import hashlib, base64, secrets
salt = base64.urlsafe_b64encode(secrets.token_bytes(16)).decode().rstrip("=")
digest = hashlib.pbkdf2_hmac("sha256", b"yourpassword", salt.encode(), 260000)
print("pbkdf2_sha256$260000$" + salt + "$" + base64.urlsafe_b64encode(digest).decode().rstrip("="))
```

---

## API surface

A few endpoints worth knowing:

```
GET  /                                          # public landing
GET  /demo/{slug}                               # public demo (read-only)
GET  /app                                       # authenticated upload page
GET  /analysis/{id}                             # analysis dashboard
GET  /analysis/{id}/export.{csv,xlsx,json}      # exports
GET  /source-page/{analysis}/{doc}/{page}.png   # rendered PDF page (for source viewer)
GET  /set-lang/{ja|en|zh}                       # switch UI language
GET  /metrics                                   # Prometheus
GET  /healthz                                   # liveness probe
```

`/analysis/demo-*` paths are public — the sidebar's mode/filter form posts there, so demo visitors can switch modes without logging in.

---

## A note on the parser

Japanese annual reports look uniform but render very differently underneath. The parser leans on three things to stay robust:

1. **Section anchors**, not page numbers. `主要な経営指標等の推移`, `連結損益計算書`, `連結財政状態計算書` etc. are matched as headings, then we scan only inside the resulting page window.
2. **Synonym ladders** per metric. Each metric (revenue, net income, equity etc.) has a prioritised list of label patterns; IFRS labels are tried first, then JGAAP, so transition-year reports pick the right column even when both tables are present.
3. **Parenthesised-annotation guard**. Sub-rows like `(27)` after 従業員数 (= 平均臨時従業員数) are detected and break collection without affecting △-marked negative numbers in cash-flow rows.

Edge cases collected so far: TIS, アバントグループ, 野村総合研究所 (JGAAP→IFRS transition, 千円 vs 百万円 units, parent-vs-consolidated indicator tables). PRs adding more samples welcome.

---

## License

MIT. See `LICENSE` if you forked this and need the text — I have not committed one to this repository yet; treat it as MIT in spirit until I do.
