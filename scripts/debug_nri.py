"""Debug CF row extraction in MAJOR section."""
from __future__ import annotations
import sys
from pathlib import Path
sys.path.insert(0, '/opt/financial-analyzer/current')

from app.pdf_parser import extract_pdf_pages, find_section_pages


def dump_cf(path_str: str, label: str) -> None:
    p = Path(path_str)
    pages, _ = extract_pdf_pages(p)
    section = find_section_pages(pages, '連結経営指標等', '(2) 提出会社', window=3)
    print(f'\n========== {label} ==========')
    for s in section:
        for i, line in enumerate(s.lines):
            if '営業活動' in line or '投資活動' in line or '財務活動' in line or 'キャッシュ' in line:
                if any(k in line for k in ['営業活動', '投資活動', '財務活動']):
                    print(f'\n  p{s.page} L{i}: "{line[:60]}"')
                    for j in range(i, min(i + 14, len(s.lines))):
                        print(f'    {j:3} {s.lines[j][:80]}')


dump_cf('/opt/financial-analyzer/demo_pdfs/3626_ＴＩＳ__2025__S100W24K_type2_pdf.pdf', 'TIS 2025')
dump_cf('/opt/financial-analyzer/demo_pdfs/4307_野村総合研究所__2024__S100TQUZ_type2_pdf.pdf', 'NRI 2024')
