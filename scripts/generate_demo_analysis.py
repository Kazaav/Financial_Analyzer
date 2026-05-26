"""Run on the SERVER to generate demo analysis from /opt/financial-analyzer/demo_pdfs/.

Usage on server:
    cd /opt/financial-analyzer/current
    /opt/financial-analyzer/venv/bin/python scripts/generate_demo_analysis.py
"""
from __future__ import annotations

import sys
from datetime import datetime
from pathlib import Path
from uuid import uuid4

# Allow import of app/* when run from project root
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.models import AnalysisRecord
from app.pdf_parser import parse_pdf
from app.storage import save_record


DEMO_PDF_DIR = Path("/opt/financial-analyzer/demo_pdfs")
DEMO_ID = "demo-it-services"


def main() -> None:
    if not DEMO_PDF_DIR.exists():
        sys.exit(f"missing dir: {DEMO_PDF_DIR}")

    pdfs = sorted(DEMO_PDF_DIR.glob("*.pdf"))
    if not pdfs:
        sys.exit("no PDFs found")

    documents = []
    for path in pdfs:
        doc_id = uuid4().hex[:10]
        original = path.name
        try:
            doc = parse_pdf(path, doc_id, original)
            documents.append(doc)
            company = (doc.company_name or "?")[:30]
            print(f"  ok  {original[:50]:50} | {company:30} | {doc.fiscal_year} | conf={doc.confidence:.2f}")
        except Exception as exc:
            print(f"  err {original}: {exc}")

    record = AnalysisRecord(
        id=DEMO_ID,
        created_at=datetime.now().strftime("%Y-%m-%d %H:%M"),
        documents=documents,
    )
    save_record(record)
    print(f"\nsaved {len(documents)} docs to demo record: {DEMO_ID}")


if __name__ == "__main__":
    main()
