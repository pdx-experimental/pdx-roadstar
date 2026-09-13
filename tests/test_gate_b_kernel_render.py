"""Gate B Test: Verifies that ProDocuX Kernel renders real PDF artifacts via execute_render_artifact.
Does NOT claim the rendered text was audited or verified.
"""
import os
import hashlib
from pathlib import Path
import pytest
import prodocux_kernel.rendering.service as rs
from prodocux_kernel.rendering.ports import ArtifactSinkPort

BASE_DIR = Path(__file__).resolve().parent.parent
EVIDENCE_DIR = BASE_DIR / "acceptance" / "evidence" / "gate_b_artifacts"


import uuid
import threading
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor

class StrictArtifactSink(ArtifactSinkPort):
    """Host-owned sink implementing OS-level atomic temp-link publishing.
    Guarantees no reader can ever observe an empty or partially written file.
    """
    def __init__(self, output_dir: Path):
        self.output_dir = output_dir
        self.records = {}
        self.action_history = defaultdict(list)
        self._lock = threading.Lock()

    def create_if_absent(self, *, output_name: str, media_type: str, payload: bytes, sha256: str):
        target_path = self.output_dir / output_name
        computed_sha = hashlib.sha256(payload).hexdigest()
        if computed_sha != sha256:
            raise ValueError(f"Payload sha256 mismatch! Expected {sha256}, got {computed_sha}")

        identity = {
            "schema_version": "prodocux_opaque_artifact_v1",
            "artifact_id": f"art-{output_name}",
            "uri": f"artifact://roadstar/artifacts/{output_name}",
            "sha256": sha256,
            "size_bytes": len(payload),
            "media_type": media_type
        }

        temp_path = self.output_dir / f"{output_name}.tmp.{uuid.uuid4().hex}"
        try:
            flags = os.O_CREAT | os.O_EXCL | os.O_WRONLY | getattr(os, "O_BINARY", 0)
            fd = os.open(temp_path, flags)
            with open(fd, "wb", closefd=True) as f:
                f.write(payload)
                f.flush()

            try:
                os.link(temp_path, target_path)
                action = "created"
            except FileExistsError:
                action = "conflict_check"
            finally:
                if temp_path.exists():
                    temp_path.unlink()

            if action == "created":
                with self._lock:
                    self.records[output_name] = {
                        "path": str(target_path),
                        "action": "created",
                        "identity": identity
                    }
                    self.action_history[output_name].append("created")
                return identity

            # Already exists: inspect digest for idempotency or conflict
            existing_bytes = target_path.read_bytes()
            existing_sha = hashlib.sha256(existing_bytes).hexdigest()
            if existing_sha == sha256:
                with self._lock:
                    self.records[output_name] = {
                        "path": str(target_path),
                        "action": "idempotent_noop",
                        "identity": identity
                    }
                    self.action_history[output_name].append("idempotent_noop")
                return identity
            else:
                raise FileExistsError(f"Artifact {output_name} already exists with different digest {existing_sha} != {sha256}")
        except Exception:
            if temp_path.exists():
                try:
                    temp_path.unlink()
                except OSError:
                    pass
            raise


def test_kernel_renders_pdf_artifact():
    sink = StrictArtifactSink(EVIDENCE_DIR)
    pdf_filename = "kernel_rendering_test.pdf"
    
    # Remove existing test artifact to ensure clean run
    test_pdf_path = EVIDENCE_DIR / pdf_filename
    if test_pdf_path.exists():
        test_pdf_path.unlink()

    req = {
        "schema_version": "prodocux_render_request_v1",
        "request_id": "req-rendering-gate-b-test",
        "target_format": "pdf",
        "output": {
            "output_name": pdf_filename,
            "delivery_mode": "artifact"
        },
        "content": {
            "schema_version": "prodocux_content_blocks_v1",
            "blocks": [
                {
                    "id": "hdr1",
                    "type": "heading",
                    "level": 1,
                    "text": "SYNTHETIC TEST ARTIFACT - PRODOCUX KERNEL RENDERING VALIDATION ONLY"
                },
                {
                    "id": "p1",
                    "type": "paragraphs",
                    "paragraphs": [
                        "Notice: This document is a technical smoke test artifact for prodocux_kernel.rendering.",
                        "It strictly tests PDF rendering capability from prodocux_content_blocks_v1.",
                        "Content herein is synthetic test data. It does NOT represent an audited or verified carrier dossier.",
                        "Test Specifications: Format=PDF, TargetMedia=application/pdf, Engine=prodocux 0.3.0rc4."
                    ]
                }
            ]
        }
    }

    http_code, result = rs.execute_render_artifact(req, sink=sink)
    assert http_code == 200, f"Render failed with code {http_code}: {result}"
    assert result["status"] == "completed"
    assert pdf_filename in sink.records

    record = sink.records[pdf_filename]
    pdf_bytes = Path(record["path"]).read_bytes()

    # Verify PDF magic bytes
    assert pdf_bytes.startswith(b"%PDF-"), "Rendered output does not have PDF magic header!"
    assert record["identity"]["media_type"] == "application/pdf"
    assert record["identity"]["size_bytes"] == len(pdf_bytes)
    assert record["identity"]["sha256"] == hashlib.sha256(pdf_bytes).hexdigest()

    # Test idempotency in sink: Calling create_if_absent with identical payload must be a no-op
    ident_res = sink.create_if_absent(
        output_name=pdf_filename,
        media_type="application/pdf",
        payload=pdf_bytes,
        sha256=record["identity"]["sha256"]
    )
    assert sink.records[pdf_filename]["action"] == "idempotent_noop"
    assert ident_res["sha256"] == record["identity"]["sha256"]

    # Test conflict detection in sink: Different payload with same output_name must raise FileExistsError
    with pytest.raises(FileExistsError) as exc_info:
        sink.create_if_absent(
            output_name=pdf_filename,
            media_type="application/pdf",
            payload=pdf_bytes + b"conflict_diff_bytes",
            sha256=hashlib.sha256(pdf_bytes + b"conflict_diff_bytes").hexdigest()
        )
    assert "already exists with different digest" in str(exc_info.value)

    print(f"\n[PASS] Kernel successfully rendered PDF: {record['path']} ({record['identity']['size_bytes']} bytes, SHA-256: {record['identity']['sha256']})")
    print(f"[PASS] StrictArtifactSink verified: Idempotent no-op on identical digest, FileExistsError on conflict.")


def test_strict_artifact_sink_concurrent_race():
    """Verify that multiple concurrent workers race atomically:
    Exactly 1 worker creates the file, remaining workers receive idempotent_noop,
    and conflicting payload raises FileExistsError without file corruption.
    """
    sink = StrictArtifactSink(EVIDENCE_DIR)
    concurrent_file = "concurrent_race_test.bin"
    concurrent_path = EVIDENCE_DIR / concurrent_file
    if concurrent_path.exists():
        concurrent_path.unlink()

    payload = b"CONCURRENT_ATOMIC_VERIFIED_PAYLOAD"
    payload_sha = hashlib.sha256(payload).hexdigest()

    worker_count = 10
    results = []

    def race_worker(worker_id: int):
        return sink.create_if_absent(
            output_name=concurrent_file,
            media_type="application/octet-stream",
            payload=payload,
            sha256=payload_sha
        )

    with ThreadPoolExecutor(max_workers=worker_count) as executor:
        futures = [executor.submit(race_worker, i) for i in range(worker_count)]
        for f in futures:
            results.append(f.result())

    # All returned identities must match the payload
    assert len(results) == worker_count
    for res in results:
        assert res["sha256"] == payload_sha

    # Target path content must match payload exactly
    assert concurrent_path.read_bytes() == payload

    # Explicitly prove and verify: Exactly 1 creation action, and exactly (worker_count - 1) idempotent no-ops
    actions = sink.action_history[concurrent_file]
    assert len(actions) == worker_count
    assert actions.count("created") == 1, f"Expected exactly 1 creation, got {actions.count('created')}"
    assert actions.count("idempotent_noop") == worker_count - 1, f"Expected {worker_count - 1} noops, got {actions.count('idempotent_noop')}"

    # Now verify that a concurrent conflict write with different payload fails atomically
    conflict_payload = b"CONFLICTING_TAMPERED_BYTES"
    conflict_sha = hashlib.sha256(conflict_payload).hexdigest()

    with pytest.raises(FileExistsError) as exc_info:
        sink.create_if_absent(
            output_name=concurrent_file,
            media_type="application/octet-stream",
            payload=conflict_payload,
            sha256=conflict_sha
        )
    assert "already exists with different digest" in str(exc_info.value)

    # Content on disk remains intact and uncorrupted
    assert concurrent_path.read_bytes() == payload
    print(f"\n[PASS] StrictArtifactSink atomic concurrency test passed: exactly 1 created, {worker_count - 1} no-ops, zero corruption.")


def test_strict_artifact_sink_no_partial_reads_under_concurrent_writers():
    """Verify that concurrent readers never observe an empty or partially written file
    while a slow writer is publishing an artifact.
    """
    sink = StrictArtifactSink(EVIDENCE_DIR)
    target_name = "partial_read_prevention_test.bin"
    target_path = EVIDENCE_DIR / target_name
    if target_path.exists():
        target_path.unlink()

    # 1 MB test payload
    chunk = b"ABCDEF0123456789" * 64
    payload = chunk * 1024  # 1 MB
    payload_sha = hashlib.sha256(payload).hexdigest()

    observed_states = []
    stop_readers = threading.Event()

    def aggressive_reader():
        while not stop_readers.is_set():
            if target_path.exists():
                try:
                    data = target_path.read_bytes()
                    observed_states.append((len(data), hashlib.sha256(data).hexdigest() == payload_sha))
                except FileNotFoundError:
                    pass

    # Launch 5 reader threads
    with ThreadPoolExecutor(max_workers=6) as executor:
        reader_futures = [executor.submit(aggressive_reader) for _ in range(5)]
        
        # Writer writes payload via atomic create_if_absent
        writer_future = executor.submit(
            sink.create_if_absent,
            output_name=target_name,
            media_type="application/octet-stream",
            payload=payload,
            sha256=payload_sha
        )
        writer_future.result()
        stop_readers.set()
        for rf in reader_futures:
            rf.result()

    assert target_path.exists()
    assert target_path.read_bytes() == payload

    # Any state observed by readers must be 100% complete; NEVER a partial or 0-byte file
    for size, matches_sha in observed_states:
        assert size == len(payload), f"Reader observed partial file size {size} != {len(payload)}!"
        assert matches_sha is True, "Reader observed corrupted data!"

    print(f"\n[PASS] Atomic publishing proved: {len(observed_states)} concurrent reads observed 0 partial bytes.")


