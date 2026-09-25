"""로컬 관점 스냅샷. 운영 데이터 수집 DB를 만들거나 수정하지 않는다."""
from __future__ import annotations

import json
import logging
import os
import re
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

LOGGER = logging.getLogger(__name__)
ID_PATTERN = re.compile(r"[a-f0-9]{32}\Z")


class SnapshotStore:
    def __init__(self, directory: Path):
        self.directory = directory

    def save(self, evidence: dict, name: str, axes: list[str], note: str) -> str:
        identifier = uuid4().hex
        payload = {
            "id": identifier, "name": name, "selected_axes": axes, "note": note,
            "saved_at": datetime.now(UTC).isoformat(), "evidence": evidence,
        }
        self.directory.mkdir(parents=True, exist_ok=True)
        temporary = self.directory / (identifier + ".tmp")
        destination = self.directory / (identifier + ".json")
        try:
            with temporary.open("x", encoding="utf-8") as stream:
                json.dump(payload, stream, ensure_ascii=False, allow_nan=False)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary, destination)
        finally:
            temporary.unlink(missing_ok=True)
        return identifier

    def get(self, identifier: str) -> dict:
        if not ID_PATTERN.fullmatch(identifier):
            raise ValueError("Invalid snapshot identifier")
        payload = json.loads((self.directory / (identifier + ".json")).read_text(encoding="utf-8"))
        if not isinstance(payload, dict) or payload.get("id") != identifier or "evidence" not in payload:
            raise ValueError("Invalid snapshot")
        return payload

    def recent(self) -> tuple[list[dict], int]:
        result, unreadable = [], 0
        paths = sorted(self.directory.glob("*.json"), key=lambda path: path.stat().st_mtime, reverse=True)
        for path in paths[:30]:
            try:
                saved = self.get(path.stem)
                result.append({key: saved[key] for key in ("id", "name", "saved_at")})
            except (OSError, ValueError, KeyError, TypeError):
                unreadable += 1
                LOGGER.warning("A local perspective snapshot could not be read")
        return result, unreadable
