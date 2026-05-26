"""Debug 従業員数 extraction for Avant."""
from __future__ import annotations
import sys
from pathlib import Path
sys.path.insert(0, '/opt/financial-analyzer/current')

from app.pdf_parser import extract_pdf_pages, find_section_pages


def dump_employees(path_str: str, label: str) -> None:
    p = Path(path_str)
    pages, _ = extract_pdf_pages(p)
    section = find_section_pages(pages, '連結経営指標等', '(2) 提出会社', window=3)
    print(f'\n========== {label} ==========')
    for s in section:
        for i, line in enumerate(s.lines):
            if '従業員' in line:
                print(f'\n  p{s.page} L{i}: "{line[:80]}"')
                for j in range(i, min(i + 18, len(s.lines))):
                    print(f'    {j:3} {s.lines[j][:80]}')
                break


dump_employees('/opt/financial-analyzer/demo_pdfs/3836_アバントグループ__2020__S100JQFT_type2_pdf.pdf', 'Avant 2020')
dump_employees('/opt/financial-analyzer/demo_pdfs/3626_ＴＩＳ__2020__S100IY60_type2_pdf.pdf', 'TIS 2020')
