"""All test artifact/resource defaults are isolated before any test runs."""
import pytest

@pytest.fixture(autouse=True)
def isolated_storage(tmp_path, monkeypatch, request):
    import dual_track_simulator as sim
    import roadstar_domain.resource_manager as resources
    import roadstar_adapter_pdx.dispatch_workflow as workflow
    import roadstar_adapter_prodocux.detention_dossier as dossier
    monkeypatch.setattr(resources, "DEFAULT_FLEET_STORAGE_DIR", tmp_path / "fleet")
    monkeypatch.setattr(resources.FleetResourceManager, "_instance", None)
    monkeypatch.setattr(workflow, "DISPATCH_RUNS_DIR", tmp_path / "runs")
    monkeypatch.setattr(dossier, "DOSSIER_DIR", tmp_path / "kernel-dossiers")
    if hasattr(request.module, "EVIDENCE_DIR"):
        evidence = tmp_path / "evidence"
        evidence.mkdir()
        monkeypatch.setattr(request.module, "EVIDENCE_DIR", evidence)
    import sys
    api = sys.modules.get("main")
    if api is not None and hasattr(api, "pdx_workflow"):
        from roadstar_application.scenario_comparison import ScenarioComparison
        monkeypatch.setattr(api, "pdx_workflow", workflow.DispatchWorkflowEngine())
        monkeypatch.setattr(api, "dual_simulator", ScenarioComparison(storage_dir=tmp_path / "api-sim"))
        monkeypatch.setattr(api, "DOSSIER_DIR", str(tmp_path / "api-dossiers"))
