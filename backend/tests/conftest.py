"""pytest configuration and fixtures for RAG-AQG backend tests."""
import sys
from pathlib import Path

# Add backend/src to sys.path so app modules can be imported directly in tests
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))
