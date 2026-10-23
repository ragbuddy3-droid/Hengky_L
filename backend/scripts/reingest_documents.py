"""Re-run extraction, chunking and indexing for documents already in the database.

Use after changing the ingestion pipeline. Each document keeps its id, owner and chat sessions; its chunks
(and their cached analyses) are replaced. Questions generated earlier still point at the old chunk ids,
so their "Sumber" tab will be empty.

Usage (from the backend/ directory, with the backend server stopped):
    uv run python scripts/reingest_documents.py
    uv run python scripts/reingest_documents.py --document-id <uuid>
"""

import argparse
import sys
from pathlib import Path

from app.core.database import get_session
from app.core.migrations import init_db
from app.models.db_models import Chunk, Document
from app.services.ingestion.pipeline import process_document
from app.services.retrieval.retriever import delete_document_vectors


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Re-ingest documents with the current pipeline.")
    parser.add_argument("--document-id", help="Only re-ingest this document")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    init_db()

    with get_session() as db:
        query = db.query(Document)
        if args.document_id:
            query = query.filter(Document.id == args.document_id)
        docs = [
            (str(d.id), str(d.filename), str(d.filepath or ""))
            for d in query.all()
        ]

    if not docs:
        print("No documents found.")
        return

    failed = 0
    for doc_id, filename, filepath in docs:
        if not filepath or not Path(filepath).exists():
            print(f"SKIP {filename}: file not found ({filepath})")
            failed += 1
            continue

        print(f"Re-ingesting {filename} ({doc_id}) ...")
        delete_document_vectors(doc_id)
        with get_session() as db:
            for chunk in db.query(Chunk).filter(Chunk.document_id == doc_id).all():
                db.delete(chunk)  # ORM delete so ChunkAnalysis rows cascade
            db.commit()

        process_document(doc_id, str(filepath))

        with get_session() as db:
            doc = db.query(Document).filter(Document.id == doc_id).one()
            status, error = str(doc.status), doc.error_message
            count = db.query(Chunk).filter(Chunk.document_id == doc_id).count()
        print(f"  -> {status}, {count} chunks" + (f" ({error})" if status == "failed" else ""))
        failed += status != "ready"

    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
