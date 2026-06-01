from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from uuid import UUID, uuid4

from pydantic import BaseModel, Field

from autoskill.core.hashing import sha256_json


class AuditRecord(BaseModel):
    audit_id: UUID = Field(default_factory=uuid4)
    occurred_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    action: str
    actor: str = "autoskill-sidecar"
    subject_type: str
    subject_id: str
    previous_hash: str | None = None
    details: dict[str, Any] = Field(default_factory=dict)
    audit_hash: str | None = None

    def sealed(self) -> "AuditRecord":
        data = self.model_dump(mode="json", exclude={"audit_hash"})
        return self.model_copy(update={"audit_hash": sha256_json(data)})


def verify_hash_chain(records: list[AuditRecord]) -> bool:
    previous: str | None = None
    for record in records:
        if record.previous_hash != previous:
            return False
        if record.sealed().audit_hash != record.audit_hash:
            return False
        previous = record.audit_hash
    return True

