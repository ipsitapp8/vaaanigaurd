"""Synthetic directory of contacts/officials (backend/app/data/directory.json)."""
import json
import re
from functools import lru_cache
from pathlib import Path

from pydantic import BaseModel

from app.services.verification import Capabilities

DATA_DIR = Path(__file__).resolve().parents[1] / "data"


class DirectoryEntry(BaseModel):
    id: str
    display_name: str
    kind: str
    role: str
    org: str | None = None
    aliases: list[str] = []
    official_numbers_masked: list[str] = []
    registered_device: bool = False
    callback_number: bool = True
    trusted_contact: bool = False
    second_approver: bool = True
    codeword: bool = True

    def capabilities(self) -> Capabilities:
        return Capabilities(
            registered_device=self.registered_device,
            callback_number=self.callback_number,
            trusted_contact=self.trusted_contact,
            second_approver=self.second_approver,
            codeword=self.codeword,
        )


@lru_cache
def load_directory() -> list[DirectoryEntry]:
    with open(DATA_DIR / "directory.json", encoding="utf-8") as f:
        return [DirectoryEntry(**e) for e in json.load(f)]


def get_entry(entry_id: str | None) -> DirectoryEntry | None:
    return next((e for e in load_directory() if e.id == entry_id), None)


def find_by_text(*phrases: str | None) -> DirectoryEntry | None:
    """First directory entry whose alias appears (as a whole word) in any phrase."""
    for phrase in phrases:
        if not phrase:
            continue
        for e in load_directory():
            for alias in e.aliases:
                if re.search(rf"(?<!\w){re.escape(alias)}(?!\w)", phrase, re.IGNORECASE):
                    return e
    return None
