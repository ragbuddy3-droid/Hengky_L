"""Who a request acts for: a logged-in account or an anonymous guest browser."""

from dataclasses import dataclass
from typing import Any

from sqlalchemy import and_, false

from app.models.db_models import ChatSession, Document

OwnedModel = type[Document] | type[ChatSession]


@dataclass(frozen=True)
class Owner:
    user_id: str | None = None
    guest_id: str | None = None

    @property
    def is_guest(self) -> bool:
        return self.user_id is None

    def clause(self, model: OwnedModel) -> Any:
        """Filter SQL untuk baris milik requester ini."""
        if self.user_id is not None:
            return model.user_id == self.user_id
        if self.guest_id is None:
            return false()  # `guest_id == None` akan menjadi IS NULL dan membuka data lama tanpa pemilik
        return and_(model.user_id.is_(None), model.guest_id == self.guest_id)

    def fields(self) -> dict[str, Any]:
        """Kolom kepemilikan untuk baris baru."""
        return {"user_id": self.user_id, "guest_id": None if self.user_id else self.guest_id}
