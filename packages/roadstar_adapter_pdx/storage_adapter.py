from __future__ import annotations

import os
import uuid
import hashlib
import threading
from pathlib import Path
from typing import Any
from collections.abc import Mapping

class RoadStarStorageAdapter:
    """Production storage adapter for RoadStar artifacts and snapshots.
    Resolves and stores artifacts under artifact://roadstar/ using atomic filesystem operations.
    """

    def __init__(self, base_dir: str | Path, uri_prefix: str = 'artifact://roadstar'):
        self.base_dir = Path(base_dir).resolve()
        self.base_dir.mkdir(parents=True, exist_ok=True)
        self.uri_prefix = uri_prefix.rstrip('/')
        self._lock = threading.Lock()

    def _uri_to_path(self, uri: str) -> Path:
        if not uri.startswith(self.uri_prefix):
            raise ValueError(f"URI '{uri}' does not match prefix '{self.uri_prefix}'")
        relative = uri[len(self.uri_prefix):].lstrip('/\\')
        target = (self.base_dir / relative).resolve()
        if not str(target).startswith(str(self.base_dir)):
            raise ValueError(f'Path traversal detected for URI \'{uri}\'')
        return target

    def _path_to_uri(self, path: Path) -> str:
        rel = path.resolve().relative_to(self.base_dir).as_posix()
        return f"{self.uri_prefix}/{rel}"
    def resolve(self, uri: str) -> bytes:
        """Resolve an opaque artifact URI and return raw payload bytes."""
        target = self._uri_to_path(uri)
        if not target.is_file():
            raise FileNotFoundError(f'Artifact not found: {uri}')
        return target.read_bytes()

    def exists(self, uri: str) -> bool:
        """Return True if the artifact exists in storage."""
        try:
            target = self._uri_to_path(uri)
            return target.is_file()
        except ValueError:
            return False

    def head(self, uri: str) -> dict[str, Any]:
        """Inspect artifact metadata."""
        target = self._uri_to_path(uri)
        if not target.is_file():
            raise FileNotFoundError(f'Artifact not found: {uri}')
        content = target.read_bytes()
        return {
            'uri': uri,
            'size_bytes': len(content),
            'sha256': hashlib.sha256(content).hexdigest(),
            'modified_at': target.stat().st_mtime,
        }

    def store(
        self,
        uri: str,
        payload: bytes,
        media_type: str = 'application/octet-stream',
    ) -> Mapping[str, Any]:
        """Atomically store an artifact. Idempotent on identical content, FileExistsError on conflict."""
        target = self._uri_to_path(uri)
        target.parent.mkdir(parents=True, exist_ok=True)
        computed_sha = hashlib.sha256(payload).hexdigest()

        temp_path = target.parent / f'{target.name}.tmp.{uuid.uuid4().hex}'
        try:
            flags = os.O_CREAT | os.O_EXCL | os.O_WRONLY | getattr(os, 'O_BINARY', 0)
            fd = os.open(temp_path, flags)
            with open(fd, 'wb', closefd=True) as f:
                f.write(payload)
                f.flush()

            try:
                os.link(temp_path, target)
                action = 'created'
            except FileExistsError:
                action = 'conflict_check'
            finally:
                if temp_path.exists():
                    try:
                        temp_path.unlink()
                    except OSError:
                        pass
            identity = {
                'schema_version': 'prodocux_opaque_artifact_v1',
                'artifact_id': f'art-{target.name}',
                'uri': uri,
                'sha256': computed_sha,
                'size_bytes': len(payload),
                'media_type': media_type,
            }

            if action == 'created':
                return identity

            existing_bytes = target.read_bytes()
            existing_sha = hashlib.sha256(existing_bytes).hexdigest()
            if existing_sha == computed_sha:
                return identity
            else:
                raise FileExistsError(
                    f'Artifact {uri} already exists with different digest {existing_sha} != {computed_sha}'
                )
        except Exception:
            if temp_path.exists():
                try:
                    temp_path.unlink()
                except OSError:
                    pass
            raise
