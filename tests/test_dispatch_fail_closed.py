"""Independent counterexamples: no success reconstructed from disk claims."""
import copy
import json
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

import pytest

from roadstar_adapter_pdx.dispatch_workflow import DispatchWorkflowEngine
from roadstar_domain.models import BackhaulMatchResult, OrderModel
from roadstar_domain.resource_manager import FileTransactionLock, FleetResourceManager, ResourceConflictError


def make_plan(root):
    manager = FleetResourceManager(root / "resources")
    engine = DispatchWorkflowEngine(storage_dir=root / "runs", resource_manager=manager)
    order = OrderModel(bill_number="B", trip_number="T", customer_name="C",
                       origin_city="MILTON", origin_prov="ON", origin_pc="",
                       dest_city="LONDON", dest_prov="ON", dest_pc="",
                       distance_miles=100, weight_lbs=30000, rate_cad=1000)
    match = BackhaulMatchResult(outbound_order=order, return_order=None,
        deadhead_reduction_pct=0, empty_miles_saved=0, total_revenue_cad=1000,
        hos_audit_passed=True, weight_audit_passed=True, assigned_driver_id=1,
        driver_name="D", notes=[])
    return engine, engine.create_dispatch_plan(match)


def test_correct_digest_and_full_fabricated_state_cannot_recover(tmp_path):
    engine, item = make_plan(tmp_path)
    run_dir = engine.storage_dir / item["run_id"]
    run_dir.mkdir()
    fake = {k: v for k, v in item.items() if k != "match_result"}
    fake["status"] = "completed"
    (run_dir / "run_state.json").write_text(json.dumps(fake))
    # Even a copied, correctly bound plan cannot establish execution provenance.
    assert engine._verify_durable_engine_run(run_dir, item["plan"], item["digest"])[0] is False
    with patch.object(engine.runtime, "execute_plan") as execute:
        with pytest.raises(RuntimeError, match="REQ-PDX-ENGINE-005"):
            engine.approve_plan(item["run_id"])
        execute.assert_not_called()


def test_ledger_failure_prevents_public_engine_entry(tmp_path):
    engine, item = make_plan(tmp_path)
    with patch.object(engine.ledger, "record", side_effect=ValueError("approval refused")):
        with patch.object(engine.runtime, "execute_plan") as execute:
            with pytest.raises(ValueError, match="approval refused"):
                engine.approve_plan(item["run_id"])
            execute.assert_not_called()


def test_attempt_persistence_failure_prevents_engine_entry(tmp_path):
    engine, item = make_plan(tmp_path)
    with patch.object(engine, "_persist_state", side_effect=OSError("disk full")):
        with patch.object(engine.runtime, "execute_plan") as execute:
            with pytest.raises(OSError, match="disk full"):
                engine.approve_plan(item["run_id"])
            execute.assert_not_called()


def test_failure_after_actual_engine_dispatch_retains_order_and_blocks_restart(tmp_path):
    engine, item = make_plan(tmp_path)
    execute = engine.runtime.execute_plan
    def crash_after_dispatch(*args):
        result = execute(*args)
        assert result["run_manifest"]["status"] == "completed"
        raise OSError("connection lost after dispatch")
    with patch.object(engine.runtime, "execute_plan", side_effect=crash_after_dispatch):
        with pytest.raises(OSError):
            engine.approve_plan(item["run_id"])
    assert len(engine.resource_manager.get_active_slots_for_trip("T")) == 3
    restarted = DispatchWorkflowEngine(storage_dir=engine.storage_dir, resource_manager=engine.resource_manager)
    with patch.object(restarted.runtime, "execute_plan") as again:
        with pytest.raises(RuntimeError, match="REQ-PDX-ENGINE-005"):
            restarted.approve_plan(item["run_id"])
        again.assert_not_called()


def test_duplicate_trip_cannot_erase_previous_slots(tmp_path):
    manager = FleetResourceManager(tmp_path)
    start = datetime(2026, 9, 12, tzinfo=timezone.utc)
    manager.acquire_reservation(truck_id="1", driver_id="1", order_bill="1",
        start_time=start, end_time=start + timedelta(hours=1), trip_id="same")
    with pytest.raises(ResourceConflictError):
        manager.acquire_reservation(truck_id="2", driver_id="2", order_bill="2",
            start_time=start, end_time=start + timedelta(hours=1), trip_id="same")
    assert len(FleetResourceManager(tmp_path).get_active_slots_for_trip("same")) == 3


def test_completion_write_failure_never_returns_success_or_releases_order(tmp_path):
    engine, item = make_plan(tmp_path)
    persist = engine._persist_state
    def fail_completion(state, path):
        if state["status"] == "completed":
            raise OSError("completion write failed")
        persist(state, path)
    with patch.object(engine, "_persist_state", side_effect=fail_completion):
        with pytest.raises(OSError, match="completion write failed"):
            engine.approve_plan(item["run_id"])
    assert engine.active_plans[item["run_id"]]["status"] == "awaiting_reconciliation"
    assert len(engine.resource_manager.get_active_slots_for_trip("T")) == 3
    run_dir = engine.storage_dir / item["run_id"]
    original = (run_dir / "run_state.json").read_bytes()
    with pytest.raises(RuntimeError, match="REQ-PDX-ENGINE-005"):
        engine.approve_plan(item["run_id"])
    assert (run_dir / "run_state.json").read_bytes() == original
    assert (run_dir / "reconciliation.json").is_file()


def test_real_process_death_releases_lock_without_deleting_file(tmp_path):
    worker = tmp_path / "holder.py"
    packages = str(Path(__file__).resolve().parents[1] / "packages")
    worker.write_text(
        "import sys,time\n"
        f"sys.path.insert(0, {packages!r})\n"
        "from pathlib import Path\n"
        "from roadstar_domain.resource_manager import FileTransactionLock\n"
        "with FileTransactionLock(Path(sys.argv[1])):\n"
        " print('LOCKED', flush=True)\n"
        " time.sleep(30)\n"
    )
    lock = tmp_path / "process.lock"
    child = subprocess.Popen([sys.executable, str(worker), str(lock)], stdout=subprocess.PIPE, text=True)
    try:
        assert child.stdout.readline().strip() == "LOCKED"
        with pytest.raises(TimeoutError):
            with FileTransactionLock(lock, timeout_sec=0.1):
                pytest.fail("live holder was bypassed")
    finally:
        child.kill()
        child.wait(timeout=5)
        child.stdout.close()
    assert lock.exists()
    with FileTransactionLock(lock, timeout_sec=0.2):
        pass
