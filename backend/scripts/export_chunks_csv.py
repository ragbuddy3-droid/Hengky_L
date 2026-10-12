"""Export chunk data from the database to a CSV file.

Usage (from the backend/ directory):
    uv run python scripts/export_chunks_csv.py
    uv run python scripts/export_chunks_csv.py --output data/chunks.csv
    uv run python scripts/export_chunks_csv.py --document-id <uuid>
    uv run python scripts/export_chunks_csv.py --subject IPAS
"""

import argparse
import csv
import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_DIR / "src"))

from app.core.database import get_session  # noqa: E402
from app.models.db_models import Chunk, Document  # noqa: E402

FIELDS = [
    "chunk_id",
    "document_id",
    "filename",
    "subject",
    "chunking_strategy",
    "chunk_index",
    "page_number",
    "chapter",
    "section_heading",
    "section_type",
    "category",
    "char_count",
    "word_count",
    "text",
    "created_at",
]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Export chunks to CSV.")
    parser.add_argument(
        "--output",
        "-o",
        type=Path,
        default=BACKEND_DIR / "data" / "chunks.csv",
        help="Output CSV path (default: backend/data/chunks.csv)",
    )
    parser.add_argument("--document-id", help="Only export chunks from this document ID")
    parser.add_argument("--subject", help="Only export chunks from documents with this subject (e.g. PJOK, IPAS)")
    return parser.parse_args()


def main() -> None:
    args = parse_args()

    with get_session() as db:
        query = (
            db.query(Chunk, Document)
            .join(Document, Chunk.document_id == Document.id)
            .order_by(Document.uploaded_at, Chunk.chunk_index)
        )
        if args.document_id:
            query = query.filter(Chunk.document_id == args.document_id)
        if args.subject:
            query = query.filter(Document.subject == args.subject)

        rows = query.all()

        args.output.parent.mkdir(parents=True, exist_ok=True)
        # utf-8-sig so Excel opens the file with correct encoding
        with open(args.output, "w", newline="", encoding="utf-8-sig") as f:
            writer = csv.DictWriter(f, fieldnames=FIELDS)
            writer.writeheader()
            for chunk, doc in rows:
                text = chunk.text or ""
                writer.writerow(
                    {
                        "chunk_id": chunk.id,
                        "document_id": chunk.document_id,
                        "filename": doc.filename,
                        "subject": doc.subject,
                        "chunking_strategy": doc.chunking_strategy,
                        "chunk_index": chunk.chunk_index,
                        "page_number": chunk.page_number,
                        "chapter": chunk.chapter,
                        "section_heading": chunk.section_heading,
                        "section_type": chunk.section_type,
                        "category": chunk.category,
                        "char_count": len(text),
                        "word_count": len(text.split()),
                        "text": text,
                        "created_at": chunk.created_at.isoformat() if chunk.created_at else "",
                    }
                )

    print(f"Exported {len(rows)} chunks to {args.output}")


if __name__ == "__main__":
    main()
