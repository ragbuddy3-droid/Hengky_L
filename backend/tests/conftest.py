"""Shared fixtures: an in-memory database behind every get_session() call and API request."""

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.core import database
from app.core.migrations import init_db
from app.services import documents


@pytest.fixture
def db_factory(monkeypatch):
    """Point the app's session factory at a fresh in-memory SQLite; returns get_session for seeding."""
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    init_db(engine)
    monkeypatch.setattr(database, "SessionLocal", sessionmaker(bind=engine, autoflush=False))
    monkeypatch.setattr(documents, "delete_document_vectors", lambda doc_id: None)  # keep ChromaDB untouched
    yield database.get_session
    engine.dispose()
