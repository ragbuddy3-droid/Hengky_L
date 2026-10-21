"""Audit PDF extraction: main-content page range and chapter mapping for every textbook in a folder.

Usage (from the backend/ directory):
    uv run python scripts/audit_extraction.py "C:\\Kuliah\\Semester 7\\Skipsi\\buku_kurikulum_merdeka"
    uv run python scripts/audit_extraction.py <folder> --only PJOK_Kelas_2

Warns when a chapter goes backwards, a chapter number is skipped, a title is missing or suspiciously long,
or a page still contains a link/barcode instruction after cleaning. Exits with status 1 if any warning is found.
"""

import argparse
import logging
import re
import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_DIR / "src"))

from app.services.ingestion.extractor import (  # noqa: E402
    MAX_TITLE_CHARS,
    NAVIGATION_REGEX,
    URL_REGEX,
    extract_pages_from_pdf,
)

CHAPTER_LABEL = re.compile(r"^Bab (\d+)(?:: (.*))?$")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Audit page range and chapter mapping of textbook PDFs.")
    parser.add_argument("folder", type=Path, help="Folder searched recursively for *.pdf")
    parser.add_argument("--only", help="Only audit files whose name contains this text")
    return parser.parse_args()


def audit(pdf_path: Path) -> list[str]:
    pages = extract_pages_from_pdf(pdf_path)
    print(f"\n## {pdf_path.name}")
    if not pages:
        print("   (no main-content pages)")
        return ["no main-content pages"]
    print(f"   pages {pages[0].page_number}-{pages[-1].page_number} ({len(pages)} pages kept)")

    warnings: list[str] = []
    prev_number = 0
    prev_label = None
    for page in pages:
        if page.chapter != prev_label:
            print(f"   p{page.page_number:<4} {page.chapter}")
            m = CHAPTER_LABEL.match(page.chapter or "")
            number = int(m.group(1)) if m else 0
            title = (m.group(2) or "") if m else ""
            if number < prev_number:
                warnings.append(f"p{page.page_number}: chapter goes back from {prev_number} to {number}")
            elif number > prev_number + 1:
                warnings.append(f"p{page.page_number}: chapter jumps from {prev_number} to {number}")
            if not title:
                warnings.append(f"p{page.page_number}: Bab {number} has no title")
            elif len(title) > MAX_TITLE_CHARS:
                warnings.append(f"p{page.page_number}: Bab {number} title is {len(title)} chars")
            prev_number, prev_label = number, page.chapter
        if URL_REGEX.search(page.text) or NAVIGATION_REGEX.search(page.text):
            warnings.append(f"p{page.page_number}: link/barcode text left after cleaning")

    for w in warnings:
        print(f"   WARNING {w}")
    return warnings


def main() -> None:
    args = parse_args()
    logging.disable(logging.CRITICAL)
    sys.stdout.reconfigure(encoding="utf-8")  # pyright: ignore[reportAttributeAccessIssue]

    pdfs = sorted(p for p in args.folder.rglob("*.pdf") if not args.only or args.only in p.name)
    total_warnings = sum(len(audit(p)) for p in pdfs)
    print(f"\n{len(pdfs)} PDF(s) audited, {total_warnings} warning(s).")
    sys.exit(1 if total_warnings else 0)


if __name__ == "__main__":
    main()
