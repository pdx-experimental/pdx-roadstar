"""Gate B Test: Verifies that public pdx_artifact_engine ArtifactRuntime resumes snapshots and natively intercepts artifact tampering."""
import os
import hashlib
import tempfile
from pathlib import Path
import pytest

from pdx_artifact_engine.runtime import ArtifactRuntime, skill_definition
from pdx_artifact_engine.dispatcher import SkillRegistry
from pdx_artifact_core.protocols import StorageAdapter
from pdx_artifact_core.snapshots import SnapshotError, create_run_snapshot
from pdx_artifact_core.approval import create_checkpoint, create_approval_request, ApprovalLedger
from pdx_artifact_core import canonical_digest


class MemoryStorageAdapter(StorageAdapter):
    def __init__(self):
        self.artifacts = {}

    def store(self, uri: str, data: bytes):
        self.artifacts[uri] = data

    def resolve(self, uri: str) -> bytes:
        if uri not in self.artifacts:
            raise KeyError(f"URI not found: {uri}")
        return self.artifacts[uri]

    def exists(self, uri: str) -> bool:
        return uri in self.artifacts


def test_public_engine_resumes_snapshot_and_intercepts_tampering():
    # 1. Setup Skill Registry with execution tools
    skill_audit = skill_definition(name="roadstar.audit_compliance", domain="fleet", description="Audit driver HOS")
    skill_dispatch = skill_definition(name="roadstar.dispatch_driver", domain="fleet", description="Dispatch to truck")
    registry = SkillRegistry([skill_audit, skill_dispatch])

    executed_steps = []

    def exec_audit(request, context=None):
        executed_steps.append("audit")
        return {
            "schema_version": "pdx_tool_result_v1",
            "tool": "roadstar.audit_compliance",
            "status": "completed",
            "output": {"compliant": True}
        }

    def exec_dispatch(request, context=None):
        executed_steps.append("dispatch")
        return {
            "schema_version": "pdx_tool_result_v1",
            "tool": "roadstar.dispatch_driver",
            "status": "completed",
            "output": {"dispatched": True}
        }

    executors = {
        "roadstar.audit_compliance": exec_audit,
        "roadstar.dispatch_driver": exec_dispatch
    }

    storage = MemoryStorageAdapter()
    runtime = ArtifactRuntime(
        registry=registry,
        executors=executors,
        storage=storage,
        missing_verifier_policy="review"
    )

    # 2. Define Execution Plan
    run_id = "run-test-gate-b-001"
    plan = {
        "schema_version": "pdx_execution_plan_v1",
        "request_id": run_id,
        "producer": {"type": "roadstar.dispatcher", "name": "PDX Autonomous Dispatch"},
        "intent": {"artifact_type": "dispatch_plan", "summary": "Dispatch driver on verified route"},
        "steps": [
            {
                "id": "step_audit",
                "kind": "tool",
                "tool": "roadstar.audit_compliance",
                "inputs": {}
            },
            {
                "id": "step_dispatch",
                "kind": "tool",
                "tool": "roadstar.dispatch_driver",
                "inputs": {}
            }
        ]
    }

    # 3. Store valid artifact in storage adapter
    artifact_uri = "artifact://roadstar/runs/run-test-gate-b-001/carrier_dossier.pdf"
    valid_payload = b"%PDF-1.4 official carrier evidence dossier bytes for roadstar"
    valid_sha256 = hashlib.sha256(valid_payload).hexdigest()
    storage.store(artifact_uri, valid_payload)

    # 4. Build official checkpoint and snapshot
    plan_dig = canonical_digest(plan)
    cp = create_checkpoint(
        plan=plan,
        run_id=run_id,
        subject_digest=plan_dig,
        completed_step_ids=["step_audit"],
        pending_step_ids=["step_dispatch"],
        evidence_digests={"audit": plan_dig},
        checkpoint_id="cp-gate-b-01"
    )

    step_receipt = {
        "schema_version": "pdx_step_receipt_v1",
        "receipt_id": "rcpt-gate-b-01",
        "step_id": "step_audit",
        "run_id": run_id,
        "status": "completed",
        "attempt": 1,
        "request_digest": "0" * 64,
        "input_digest": "0" * 64,
        "output_digest": "0" * 64,
        "recorded_at": "2026-09-11T00:00:00Z",
        "output_bindings": [
            {
                "name": "carrier_dossier",
                "artifact": {
                    "artifact_id": "art-01",
                    "uri": artifact_uri,
                    "media_type": "application/pdf",
                    "created_at": "2026-09-11T00:00:00Z",
                    "size_bytes": len(valid_payload),
                    "sha256": valid_sha256
                }
            }
        ]
    }

    snapshot = create_run_snapshot(
        checkpoint=cp,
        step_receipts=[step_receipt],
        state="awaiting_approval",
        snapshot_id="snap-gate-b-01"
    )

    decision = {
        "schema_version": "pdx_approval_decision_v1",
        "decision_id": "dec-gate-b-01",
        "approval_request_id": "req-gate-b-01",
        "checkpoint_id": cp["checkpoint_id"],
        "idempotency_key": "idem-gate-b-01",
        "actor_id": "dispatcher@roadstar.ca",
        "decision": "approved",
        "subject_digest": plan_dig,
        "plan_digest": plan_dig,
        "evidence_digests": {"audit": plan_dig},
        "decided_at": "2026-09-11T00:00:00Z"
    }

    # 5. Normal Resumption: must succeed
    with tempfile.TemporaryDirectory() as td:
        res = runtime.resume_snapshot(plan, snapshot, decision, td)
        assert res["run_manifest"]["status"] == "completed"
        assert "dispatch" in executed_steps
        print("\n[PASS] Normal snapshot resumption completed successfully via public Engine.")

    # 6. Tampering Detection: Modify exactly 1 byte in storage (same length, flipped byte)
    tampered_payload = b"%PDF-1.4 official carrier evidence dossier bytes for roadstaX"
    assert len(tampered_payload) == len(valid_payload)
    assert tampered_payload != valid_payload
    storage.store(artifact_uri, tampered_payload)
    executed_steps.clear()  # Reset executor tracking

    # 7. Resume with tampered artifact: Must be natively intercepted by public ArtifactRuntime
    with tempfile.TemporaryDirectory() as td:
        with pytest.raises(SnapshotError) as exc_info:
            runtime.resume_snapshot(plan, snapshot, decision, td)
        
        err_msg = str(exc_info.value)
        assert "snapshot artifact digest mismatch" in err_msg, f"Unexpected error message: {err_msg}"
        # Assert that the downstream tool executor was NEVER invoked
        assert len(executed_steps) == 0, f"Downstream tools were executed despite tampering: {executed_steps}"
        print(f"[PASS] Public ArtifactRuntime natively intercepted 1-byte artifact tampering:\n  {err_msg}")
        print(f"[PASS] Verified: Zero downstream steps executed after tampering failure.")
