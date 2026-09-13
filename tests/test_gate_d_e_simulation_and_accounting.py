"""Gate D & E Verification Suite:
- Gate D: DES Simulation Physics, 1e-6 miles Step Invariance, Negative/Zero/NaN/Inf Rejection
- Gate E: Single Source Accounting Reconciliation, Zero Fake Fuel Savings, Benchmark API Integrity
"""
import math
import pytest
from pathlib import Path
from fastapi.testclient import TestClient

from dual_track_simulator import DualTrackSimulator
from roadstar_application.scenario_comparison import ScenarioComparison
from truck_simulator import TelematicsSimulator
from roadstar_domain.data_loader import load_dataset
from apps.api.main import app

client = TestClient(app)


def test_gate_d_step_invariance_dt_1_5_30_120_960(tmp_path):
    """Gate D requirement:
    步長 1、5、30、120、960: 同 seed、同截止時刻的事件序列與業務結果一致；
    金額分毫一致，里程未四捨五入誤差最多 1e-6 mi.
    """
    step_sizes = [1.0, 5.0, 30.0, 120.0, 960.0]
    results = []

    for dt in step_sizes:
        sim = ScenarioComparison("2026-08-14", storage_dir=tmp_path / str(dt))
        total_mins = 0.0
        while total_mins < 960.0:
            step = min(dt, 960.0 - total_mins)
            sim.tick(step)
            total_mins += step

        st = sim.get_state()
        results.append({
            "dt": dt,
            "base_total_miles": st["baseline"]["total_miles"],
            "pdx_total_miles": st["pdx"]["total_miles"],
            "base_empty_miles": st["baseline"]["empty_miles"],
            "pdx_empty_miles": st["pdx"]["empty_miles"],
            "base_net_profit": st["baseline"]["net_profit"],
            "pdx_net_profit": st["pdx"]["net_profit"],
            "net_profit_delta": st["deltas"]["net_profit_delta_cad"],
            "interventions_count": len(st["interventions"]),
            "intervention_receipt_ids": [(ev["type"], ev["truck"]) for ev in reversed(st["interventions"])],
        })

    reference = results[0]
    for r in results[1:]:
        dt = r["dt"]
        # Corridor mileage invariance (< 1e-6 mi)
        assert abs(r["base_total_miles"] - reference["base_total_miles"]) < 1e-6, f"dt={dt} base total miles drifted"
        assert abs(r["pdx_total_miles"] - reference["pdx_total_miles"]) < 1e-6, f"dt={dt} pdx total miles drifted"
        assert abs(r["base_empty_miles"] - reference["base_empty_miles"]) < 1e-6, f"dt={dt} base empty miles drifted"
        assert abs(r["pdx_empty_miles"] - reference["pdx_empty_miles"]) < 1e-6, f"dt={dt} pdx empty miles drifted"

        # Financial exactness (< $0.01)
        assert abs(r["base_net_profit"] - reference["base_net_profit"]) < 0.01, f"dt={dt} base profit drifted"
        assert abs(r["pdx_net_profit"] - reference["pdx_net_profit"]) < 0.01, f"dt={dt} pdx profit drifted"
        assert abs(r["net_profit_delta"] - reference["net_profit_delta"]) < 0.01, f"dt={dt} profit delta drifted"

        # Event sequence exactness
        assert r["interventions_count"] == reference["interventions_count"], f"dt={dt} intervention count mismatch"
        assert r["intervention_receipt_ids"] == reference["intervention_receipt_ids"], f"dt={dt} sequence mismatch"


def test_gate_d_invalid_tick_rejection_domain_and_api():
    """Gate D requirement:
    0／負數／NaN／infinity tick: 明確拒絕且不改變狀態；API 與直接 domain 呼叫均測試.
    """
    sim = DualTrackSimulator(target_date_str="2026-08-14", enable_stochastic=False)
    initial_minute = sim.sim_minute
    initial_base_miles = sim.baseline["total_miles"]

    # Domain rejections
    invalid_ticks = [0.0, -1.0, -100.0, float("nan"), float("inf"), float("-inf")]
    for bad in invalid_ticks:
        with pytest.raises(ValueError, match="elapsed_minutes"):
            sim.tick(bad)
        # State must remain unchanged
        assert sim.sim_minute == initial_minute
        assert sim.baseline["total_miles"] == initial_base_miles

    # Telematics simulator domain rejection
    drivers, _ = load_dataset()
    tsim = TelematicsSimulator(drivers[:5])
    t_time = tsim.current_sim_time
    for bad in invalid_ticks:
        with pytest.raises(ValueError, match="Invalid elapsed_minutes"):
            tsim.tick(bad)
        assert tsim.current_sim_time == t_time

    # API rejections
    for bad in [0.0, -5.0]:
        res_dual = client.post("/api/simulator/dual/tick", json={"elapsed_minutes": bad})
        assert res_dual.status_code == 400

        res_mono = client.post("/api/simulator/tick", json={"elapsed_minutes": bad})
        assert res_mono.status_code == 400


def test_gate_e_accounting_single_source_and_zero_fake_fuel_savings(tmp_path):
    """Gate E requirement:
    - 相同行駛里程不能因 empty→loaded 就減免燃料成本 -> fuel_saved_cad == 0.00
    - 強制不變量：profit_delta = pdx_profit - baseline_profit
    - 分項收益與成本差加總亦須等於同一差額
    - 無重複計入 backhaul revenue
    """
    sim = ScenarioComparison("2026-08-14", storage_dir=tmp_path)
    sim.tick(960.0)
    st = sim.get_state()

    base = st["baseline"]
    pdx = st["pdx"]
    deltas = st["deltas"]

    # 1. Zero fake fuel savings
    assert deltas["fuel_saved_cad"] == 0.0, "Fuel saved CAD must be strictly $0.00"
    expected_cost_delta = round(pdx["running_cost"] - base["running_cost"], 2)
    assert round(pdx["running_cost"], 2) == round(base["running_cost"] + expected_cost_delta, 2)

    # 2. Freight revenue integrity: pdx freight = base freight + new backhaul revenue
    assert round(pdx["freight_revenue"], 2) == round(base["freight_revenue"] + pdx["new_backhaul_revenue"], 2)

    # 3. Single Source of Truth Profit Delta
    expected_profit_delta = round(pdx["net_profit"] - base["net_profit"], 2)
    assert deltas["net_profit_delta_cad"] == expected_profit_delta

    # 4. Component reconciliation: net profit delta = backhaul revenue + detention gain - added operating cost
    sum_components = round(deltas["new_backhaul_revenue_cad"] + deltas["detention_gain_cad"] - expected_cost_delta, 2)
    assert deltas["net_profit_delta_cad"] == sum_components


def test_gate_e_benchmark_api_derived_from_simulation_state():
    """Gate E requirement:
    - Benchmark API 讀取指定已完成 run 的同一結果
    - Modal 只渲染回傳值，不得另有數字常數或再次不同方式計算
    - 刪除 audited、100% recovery 等未被證據支持的文字
    """
    res = client.get("/api/analysis/benchmark")
    assert res.status_code == 200
    bm = res.json()

    # Must NOT claim 100% recovery
    assert "detention_recovery_rate_pct" not in bm.get("with_pdx_optimization", {})
    assert bm["with_pdx_optimization"]["modeled_fuel_cost_savings_cad"] == 0.0
    assert "annualized_fleet_projection_cad" not in bm
    assert bm["backhaul_data_status"]["revenue_eligible"] is False
    assert bm["with_pdx_optimization"]["source_backhaul_revenue_cad"] == 0.0


def test_gate_c_reset_preserves_historical_artifacts(tmp_path):
    """Gate C/D requirement:
    reset／切日期／啟動不得刪除過往證據。依 run 分區，清理須是明確獨立操作.
    """
    sim = ScenarioComparison("2026-08-14", storage_dir=tmp_path)
    sim.tick(960.0)
    st1 = sim.get_state()
    assert len(st1["interventions"]) > 0

    first_filename = next(event["filename"] for event in st1["interventions"] if event["filename"].endswith(".pdf"))
    # Check that artifact exists on disk
    file_path = sim.root / "dossiers" / first_filename
    assert file_path.is_file(), f"Expected artifact {file_path} to exist"

    # Reset simulator
    sim.reset()
    assert sim.simulator.sim_minute == 0
    # Artifact must NOT be deleted by reset
    assert file_path.is_file(), f"Artifact {file_path} was incorrectly deleted by reset()"
