"""Dump MAJOR section pages content for TIS, NRI, Avant."""
from __future__ import annotations
import sys
from pathlib import Path
sys.path.insert(0, '/opt/financial-analyzer/current')

from app.pdf_parser import extract_pdf_pages, find_section_pages


def dump_major(path_str: str, label: str) -> None:
    p = Path(path_str)
    pages, _ = extract_pdf_pages(p)
    section = find_section_pages(pages, '連結経営指標等', '(2) 提出会社', window=3)
    print(f'\n========== {label} ==========')
    for s in section:
        print(f'\n--- p{s.page} ---')
        for i, line in enumerate(s.lines):
            if i > 70:
                print(f'  ... (more lines truncated)')
                break
            print(f'  {i:3} {line[:90]}')


# TIS 2020 - check net_income extraction issue
dump_major('/opt/financial-analyzer/demo_pdfs/3626_ＴＩＳ__2020__S100IY60_type2_pdf.pdf', 'TIS 2020')

# NRI 2022 - check why NA frozen
dump_major('/opt/financial-analyzer/demo_pdfs/4307_野村総合研究所__2022__S100OBJK_type2_pdf.pdf', 'NRI 2022 (full)')

# Avant 2024 - check unit detection
dump_major('/opt/financial-analyzer/demo_pdfs/3836_アバントグループ__2024__S100UEH8_type2_pdf.pdf', 'Avant 2024')
