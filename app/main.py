from __future__ import annotations

import re
from datetime import datetime
from pathlib import Path
from urllib.parse import urlencode
from uuid import uuid4

from fastapi import FastAPI, File, Form, HTTPException, Query, Request, UploadFile
from fastapi.responses import FileResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from .analysis import METRIC_ORDER, build_analysis
from .auth import authenticate, clear_login_cookie, login_redirect, read_session_user, require_admin, set_login_cookie
from .cleanup import is_demo_id, maybe_cleanup_expired_storage
from .ai_providers import get_ai_provider
from .formatting import fmt_metric, fmt_money, fmt_money_compact, fmt_number, fmt_percent, fmt_ratio, score_label
from .models import AnalysisRecord, FinancialDocument
from .pdf_parser import parse_pdf
from .reporting import generate_report
from .settings import REPORT_DIR, STATIC_DIR, TEMPLATES_DIR, UPLOAD_DIR, ensure_storage
from .storage import list_records, load_record, save_record


ensure_storage()
maybe_cleanup_expired_storage(force=True)

app = FastAPI(title="Financial PDF Analyzer", version="0.3.0")
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

templates = Jinja2Templates(directory=str(TEMPLATES_DIR))
templates.env.filters["number"] = fmt_number
templates.env.filters["money"] = fmt_money
templates.env.filters["money_compact"] = fmt_money_compact
templates.env.filters["percent"] = fmt_percent
templates.env.filters["ratio"] = fmt_ratio
templates.env.filters["metric"] = fmt_metric
templates.env.filters["score_label"] = score_label


PUBLIC_PATHS = ("/login", "/static", "/favicon.ico", "/healthz", "/demo")
ROOT_PUBLIC_PATHS = {"/"}


DEMO_REGISTRY: dict[str, dict] = {
    "timeseries-nri": {
        "analysis_id": "demo-it-services",
        "title": "野村総合研究所 · 6年間の財務推移",
        "subtitle": "同一企業時系列モード · JGAAP→IFRS 移行を含む経年変化",
        "default_mode": "same_company",
        "preset": {"selected_company": "4307"},
    },
    "cross-section-2024": {
        "analysis_id": "demo-it-services",
        "title": "IT サービス3社 · 2024年度横断比較",
        "subtitle": "多社同年度モード · 同業3社のKPI を一画面で比較",
        "default_mode": "same_year",
        "preset": {"selected_year": "2024"},
    },
    "custom-all": {
        "analysis_id": "demo-it-services",
        "title": "全PDF カスタム比較",
        "subtitle": "カスタムモード · 3社 × 6年 = 18 PDF を自由に組み合わせ",
        "default_mode": "custom",
        "include_all_docs": True,
    },
}


@app.middleware("http")
async def auth_and_cleanup_middleware(request: Request, call_next):
    maybe_cleanup_expired_storage()
    path = request.url.path
    if path in ROOT_PUBLIC_PATHS or path.startswith(PUBLIC_PATHS):
        return await call_next(request)

    user = read_session_user(request)
    if not user:
        return login_redirect(request)
    request.state.user = user
    return await call_next(request)


@app.get("/healthz")
async def healthz():
    return {"ok": True}


@app.get("/")
async def landing_page(request: Request):
    user = read_session_user(request)
    demos = []
    for slug, meta in DEMO_REGISTRY.items():
        params: dict[str, str] = {"mode": meta.get("default_mode", "same_year")}
        for k, v in meta.get("preset", {}).items():
            params[k] = str(v)
        href = f"/demo/{slug}?{urlencode(params)}"
        demos.append({
            "slug": slug,
            "title": meta["title"],
            "subtitle": meta["subtitle"],
            "href": href,
        })
    return templates.TemplateResponse(
        request,
        "landing.html",
        {"demos": demos, "current_user": user},
    )


@app.get("/login")
async def login_page(request: Request, next: str = "/app"):
    if read_session_user(request):
        return RedirectResponse(url=next if next.startswith("/") and not next.startswith("//") else "/app", status_code=303)
    return templates.TemplateResponse(request, "login.html", {"next": next, "error": ""})


@app.post("/login")
async def login_submit(
    request: Request,
    username: str = Form(""),
    password: str = Form(""),
    next: str = Form("/app"),
):
    user = authenticate(username.strip(), password)
    if not user:
        return templates.TemplateResponse(
            request,
            "login.html",
            {"next": next, "error": "ユーザー名またはパスワードが正しくありません。"},
            status_code=401,
        )
    target = next if next.startswith("/") and not next.startswith("//") else "/app"
    response = RedirectResponse(url=target, status_code=303)
    set_login_cookie(response, user)
    return response


@app.get("/logout")
async def logout():
    response = RedirectResponse(url="/", status_code=303)
    clear_login_cookie(response)
    return response


def safe_filename(filename: str) -> str:
    name = Path(filename).name
    name = re.sub(r"[^\w.\-一-龥ぁ-んァ-ヶー・（）()]+", "_", name, flags=re.UNICODE)
    return name[:120] or "uploaded.pdf"


def parse_optional_int(value: str | int | None) -> int | None:
    if value in (None, ""):
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def parse_float_form(value: str | None) -> float | None:
    if value is None:
        return None
    value = value.strip().replace(",", "")
    if not value:
        return None
    negative = value.startswith("△") or value.startswith("▲") or value.startswith("(")
    value = re.sub(r"[^\d.\-]", "", value)
    try:
        parsed = float(value)
    except ValueError:
        return None
    return -abs(parsed) if negative else parsed


def error_document(doc_id: str, filename: str, stored_path: Path, message: str) -> FinancialDocument:
    return FinancialDocument(
        id=doc_id,
        filename=filename,
        stored_path=str(stored_path),
        company_name=Path(filename).stem,
        fiscal_year=None,
        fiscal_period="",
        unit="百万円",
        page_count=0,
        char_count=0,
        text_excerpt="",
        metrics={key: None for key in METRIC_ORDER},
        extraction_notes=[f"PDF解析エラー: {message}"],
        confidence=0.0,
    )


async def parse_uploaded_pdfs(analysis_id: str, files: list[UploadFile]) -> list[FinancialDocument]:
    pdfs = [file for file in files if file.filename and file.filename.lower().endswith(".pdf")]
    if not pdfs:
        raise HTTPException(status_code=400, detail="PDFファイルを選択してください。")

    documents: list[FinancialDocument] = []
    for upload in pdfs:
        original = safe_filename(upload.filename or "uploaded.pdf")
        doc_id = uuid4().hex[:10]
        stored_path = UPLOAD_DIR / f"{analysis_id}-{doc_id}-{original}"
        stored_path.write_bytes(await upload.read())
        try:
            document = parse_pdf(stored_path, doc_id, original)
        except Exception as exc:
            document = error_document(doc_id, original, stored_path, str(exc))
        documents.append(document)
    return documents


def reject_demo_mutation(analysis_id: str) -> None:
    if is_demo_id(analysis_id):
        raise HTTPException(status_code=403, detail="デモデータは編集できません。")


@app.get("/app")
async def app_index(request: Request):
    provider = get_ai_provider()
    return templates.TemplateResponse(
        request,
        "index.html",
        {
            "recent_records": list_records(),
            "ai_provider": provider.name,
            "ai_configured": provider.is_configured(),
            "current_user": request.state.user,
        },
    )


@app.post("/upload")
async def upload_pdfs(files: list[UploadFile] = File(...)):
    analysis_id = datetime.now().strftime("%Y%m%d%H%M%S") + "-" + uuid4().hex[:6]
    documents = await parse_uploaded_pdfs(analysis_id, files)
    record = AnalysisRecord(
        id=analysis_id,
        created_at=datetime.now().strftime("%Y-%m-%d %H:%M"),
        documents=documents,
    )
    save_record(record)
    return RedirectResponse(url=f"/analysis/{analysis_id}", status_code=303)


@app.post("/analysis/{analysis_id}/upload")
async def append_pdfs(analysis_id: str, files: list[UploadFile] = File(...)):
    reject_demo_mutation(analysis_id)
    try:
        record = load_record(analysis_id)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    documents = await parse_uploaded_pdfs(analysis_id, files)
    record.documents.extend(documents)
    save_record(record)
    return RedirectResponse(url=f"/analysis/{analysis_id}?added={len(documents)}", status_code=303)


@app.post("/analysis/{analysis_id}/reparse")
async def reparse_documents(request: Request, analysis_id: str):
    require_admin(request)
    reject_demo_mutation(analysis_id)
    try:
        record = load_record(analysis_id)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    reparsed: list[FinancialDocument] = []
    for old_doc in record.documents:
        path = Path(old_doc.stored_path)
        if not path.exists():
            old_doc.extraction_notes.append("保存済みPDFが見つからないため再解析できませんでした。")
            reparsed.append(old_doc)
            continue
        try:
            new_doc = parse_pdf(path, old_doc.id, old_doc.filename)
        except Exception as exc:
            new_doc = error_document(old_doc.id, old_doc.filename, path, str(exc))
        reparsed.append(new_doc)
    record.documents = reparsed
    save_record(record)
    return RedirectResponse(url=f"/analysis/{analysis_id}?reparsed=1", status_code=303)


def _render_analysis_page(
    request: Request,
    analysis_id: str,
    mode: str,
    selected_year: str | None,
    selected_company: str | None,
    selected_docs: list[str],
    chart_type: str | None,
    report_file: str | None,
    added: str | None,
    reparsed: str | None,
    deleted: str | None,
    is_demo: bool,
    current_user,
    demo_meta: dict | None = None,
):
    try:
        record = load_record(analysis_id)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    analysis = build_analysis(
        record,
        mode=mode,
        selected_year=parse_optional_int(selected_year),
        selected_company=selected_company,
        selected_doc_ids=selected_docs,
        chart_type=chart_type,
    )
    return templates.TemplateResponse(
        request,
        "analysis.html",
        {
            "analysis": analysis,
            "report_file": report_file,
            "added": added,
            "reparsed": reparsed,
            "deleted": deleted,
            "current_user": current_user,
            "is_demo": is_demo,
            "demo_meta": demo_meta,
        },
    )


@app.get("/analysis/{analysis_id}")
async def analysis_page(
    request: Request,
    analysis_id: str,
    mode: str = Query("same_year"),
    selected_year: str | None = Query(None),
    selected_company: str | None = Query(None),
    selected_docs: list[str] = Query(default=[]),
    chart_type: str | None = Query(None),
    report_file: str | None = Query(None),
    added: str | None = Query(None),
    reparsed: str | None = Query(None),
    deleted: str | None = Query(None),
):
    return _render_analysis_page(
        request,
        analysis_id,
        mode,
        selected_year,
        selected_company,
        selected_docs,
        chart_type,
        report_file,
        added,
        reparsed,
        deleted,
        is_demo=is_demo_id(analysis_id),
        current_user=request.state.user,
    )


@app.get("/demo/{slug}")
async def demo_page(
    request: Request,
    slug: str,
    mode: str | None = Query(None),
    selected_year: str | None = Query(None),
    selected_company: str | None = Query(None),
    selected_docs: list[str] = Query(default=[]),
    chart_type: str | None = Query(None),
):
    meta = DEMO_REGISTRY.get(slug)
    if not meta:
        raise HTTPException(status_code=404, detail="demo not found")

    resolved_mode = mode or meta.get("default_mode", "same_year")
    preset = meta.get("preset", {})
    resolved_year = selected_year if selected_year is not None else preset.get("selected_year")
    resolved_company = selected_company if selected_company is not None else preset.get("selected_company")

    # For custom mode demos with include_all_docs flag, select all PDFs by default
    resolved_doc_ids = list(selected_docs)
    if resolved_mode == "custom" and not resolved_doc_ids and meta.get("include_all_docs"):
        try:
            rec = load_record(meta["analysis_id"])
            resolved_doc_ids = [d.id for d in rec.documents]
        except FileNotFoundError:
            pass

    return _render_analysis_page(
        request,
        meta["analysis_id"],
        resolved_mode,
        resolved_year,
        resolved_company,
        resolved_doc_ids,
        chart_type,
        report_file=None,
        added=None,
        reparsed=None,
        deleted=None,
        is_demo=True,
        current_user=read_session_user(request),
        demo_meta={"slug": slug, **meta},
    )


@app.post("/analysis/{analysis_id}/documents/delete")
async def delete_documents(
    request: Request,
    analysis_id: str,
    selected_delete_docs: list[str] = Form(default=[]),
    mode: str = Form("same_year"),
    selected_year: str | None = Form(None),
    selected_company: str | None = Form(None),
    chart_type: str | None = Form(None),
):
    require_admin(request)
    reject_demo_mutation(analysis_id)
    try:
        record = load_record(analysis_id)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    delete_ids = {doc_id for doc_id in selected_delete_docs if doc_id}
    deleted_count = 0
    kept: list[FinancialDocument] = []
    upload_root = UPLOAD_DIR.resolve()

    for doc in record.documents:
        if doc.id not in delete_ids:
            kept.append(doc)
            continue
        deleted_count += 1
        stored_path = Path(doc.stored_path)
        try:
            resolved = stored_path.resolve()
            if resolved.exists() and resolved.is_file() and resolved.is_relative_to(upload_root):
                resolved.unlink()
        except OSError:
            pass

    if deleted_count:
        record.documents = kept
        save_record(record)

    params: dict[str, str] = {"mode": mode, "deleted": str(deleted_count)}
    if selected_year:
        params["selected_year"] = selected_year
    if selected_company and selected_company not in delete_ids:
        params["selected_company"] = selected_company
    if chart_type:
        params["chart_type"] = chart_type
    return RedirectResponse(url=f"/analysis/{analysis_id}?{urlencode(params)}", status_code=303)


@app.post("/analysis/{analysis_id}/documents/{doc_id}")
async def update_document(request: Request, analysis_id: str, doc_id: str):
    require_admin(request)
    reject_demo_mutation(analysis_id)
    try:
        record = load_record(analysis_id)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    form = await request.form()
    target = next((doc for doc in record.documents if doc.id == doc_id), None)
    if not target:
        raise HTTPException(status_code=404, detail="document not found")

    target.security_code = re.sub(r"\D", "", str(form.get("security_code") or target.security_code))[:4]
    target.edinet_code = str(form.get("edinet_code") or target.edinet_code).strip().upper()
    target.company_name = str(form.get("company_name") or target.company_name).strip() or target.company_name
    target.fiscal_year = parse_optional_int(str(form.get("fiscal_year") or "")) or target.fiscal_year
    target.unit = str(form.get("unit") or target.unit).strip() or target.unit
    for key in METRIC_ORDER:
        if f"metric_{key}" in form:
            target.metrics[key] = parse_float_form(str(form.get(f"metric_{key}") or ""))
    target.extraction_notes.append("ユーザー編集により抽出値を更新しました。")
    save_record(record)
    return RedirectResponse(url=f"/analysis/{analysis_id}", status_code=303)


@app.post("/analysis/{analysis_id}/report")
async def create_report(
    analysis_id: str,
    mode: str = Form("same_year"),
    selected_year: str | None = Form(None),
    selected_company: str | None = Form(None),
    selected_docs: list[str] = Form(default=[]),
    chart_type: str | None = Form(None),
):
    try:
        record = load_record(analysis_id)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    report_path = generate_report(
        record,
        mode=mode,
        selected_year=parse_optional_int(selected_year),
        selected_company=selected_company,
        selected_doc_ids=selected_docs,
        chart_type=chart_type,
    )
    url = f"/analysis/{analysis_id}?mode={mode}&report_file={report_path.name}"
    if selected_year:
        url += f"&selected_year={selected_year}"
    if selected_company:
        url += f"&selected_company={selected_company}"
    if chart_type:
        url += f"&chart_type={chart_type}"
    for doc_id in selected_docs:
        url += f"&selected_docs={doc_id}"
    return RedirectResponse(url=url, status_code=303)


@app.get("/reports/{filename}")
async def download_report(filename: str):
    path = REPORT_DIR / Path(filename).name
    if not path.exists():
        raise HTTPException(status_code=404, detail="report not found")
    return FileResponse(path, media_type="text/html", filename=path.name)
