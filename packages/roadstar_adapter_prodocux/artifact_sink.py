from __future__ import annotations

import os
import uuid
import hashlib
import threading
from pathlib import Path
from typing import Any
from collections import defaultdict
from collections.abc import Mapping

class RoadStarArtifactSink:
    """Production sink for ProDocuX Kyrnel rendering artifacts.
    Atomically publishes artifacts via temp-file + os.link to prevent partial reads.
    """

    def __init__(self, base_dir: str | Path, uri_prefix: str = 'artifact://roadstar/artifacts'):
        self.base_dir = Path(base_dir).resolve()
        self.base_dir.mkdir(parents=True, exist_ok=True)
        self.uri_prefix = uri_prefix.rstrip('/')
        self.records: dict[str, dict[str, Any]] = {}
        self.action_history = defaultdict(list)
        self._lock = threading.Lock()

    def create_if_absent(
        self,
        *,
        output_name: str,
        media_type: str,
        payload: bytes,
        sha256: str,
    ) -> Mapping[str, Any]:
        target_path = self.base_dir / output_name
        computed_sha = hashlib.sha256(payload).hexdigest()
        if computed_sha != sha256:
            raise ValueError(f'Payload sha256 mismatch! Expected {sha256}, got {computed_sha}')

        identity = {
            'schema_version': 'prodocux_opaque_artifact_v1',
            'artifact_id': f'art-{output_name}',
            'uri': f'{self.uri_prefix}/{output_name}',
            'sha256': sha256,
            'size_bytes': len(payload),
            'media_type': media_type,
        }

        temp_path = self.base_dir / f"{output_name}.tmp.{uuid.uuid4().hex}"
        try:
            flags = os.O_CREAT | os.O_EXCL | os.O_WRONLY | getattr(os, 'O_BINARY', 0)
            fd = os.open(temp_path, flags)
            with open(fd, 'wb', closefd=True) as f:
                f.write(payload)
                f.flush()

            try:
                os.link(temp_path, target_path)
                action = 'created'
            except FileExistsError:
                action = 'conflict_check'
            finally:
                if temp_path.exists():
                    try:
                        temp_path.unlink()
                    except OSError:
                        pass

            if action == 'created':
                with self._lock:
                    self.records[output_name] = {
                        'path': str(target_path),
                        'action': 'created',
                        'identity': identity,
                    }
                    self.action_history[output_name].append('created')
                return identity

            existing_bytes = target_path.read_bytes()
            existing_sha = hashlib.sha256(existing_bytes).hexdigest()
            if existing_sha == sha256:
                with self._lock:
                    self.records[output_name] = {
                        'path': str(target_path),
                        'action': 'idempotent_noop',
                        'identity': identity,
                    }
                    self.action_history[output_name].append('idempotent_noop')
                return identity
            else:
                raise FileExistsError(
                    f'Artifact {output_name} already exists with different digest {existing_sha} != {sha256}'
                )
        except Exception:
            if temp_path.exists():
                try:
                    temp_path.unlink()
                except OSError:
                    pass
            raise
