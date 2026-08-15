"""API v1 router aggregator."""
from fastapi import APIRouter
from app.api.v1.documents import router as documents_router
from app.api.v1.chat import router as chat_router
from app.api.v1.questions import router as questions_router

router = APIRouter(prefix="/v1")
router.include_router(documents_router)
router.include_router(chat_router)
router.include_router(questions_router)
