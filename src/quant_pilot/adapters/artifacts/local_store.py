"""Local-filesystem ArtifactStore. S3/MinIO adapter can replace it behind the same port.

Keys are relative paths under base_dir; any key that resolves outside base_dir is rejected
(path-traversal guard).
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from quant_pilot.domain.models import ArtifactRef


class LocalArtifactStore:
    def __init__(self, base_dir: str | os.PathLike[str]) -> None:
        self.base = Path(base_dir).resolve()
        self.base.mkdir(parents=True, exist_ok=True)

    def _resolve(self, key: str) -> Path:
        path = (self.base / key).resolve()
        if path != self.base and not str(path).startswith(str(self.base) + os.sep):
            raise ValueError(f"unsafe artifact key escapes base dir: {key!r}")
        return path

    def save_bytes(
        self, key: str, data: bytes, content_type: str = "application/octet-stream"
    ) -> ArtifactRef:
        path = self._resolve(key)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
        return ArtifactRef(key=key, uri=path.as_uri(), size=len(data), content_type=content_type)

    def save_json(self, key: str, obj: Any) -> ArtifactRef:
        data = json.dumps(obj, default=str).encode("utf-8")
        return self.save_bytes(key, data, content_type="application/json")

    def load_bytes(self, key: str) -> bytes:
        return self._resolve(key).read_bytes()

    def load_json(self, key: str) -> Any:
        return json.loads(self.load_bytes(key))

    def exists(self, key: str) -> bool:
        try:
            return self._resolve(key).is_file()
        except ValueError:
            return False

    def uri_for(self, key: str) -> str:
        return self._resolve(key).as_uri()
