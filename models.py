from dataclasses import dataclass, field
from typing import Literal
import uuid

Status = Literal["pending", "success", "failed", "unrecognized", "ambiguous"]


@dataclass
class AddressItem:
    display_text: str
    raw_text: str
    source_location: str
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    status: Status = "pending"

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "raw_text": self.raw_text,
            "display_text": self.display_text,
            "source_location": self.source_location,
            "status": self.status,
        }
