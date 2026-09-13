"""Runs Gate B tests and records structured evidence into acceptance/evidence/gate_b_report.json."""
import sys
import json
import subprocess
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
EVIDENCE_DIR = BASE_DIR / "acceptance" / "evidence"
VENV_PYTHON = BASE_DIR / ".acceptance_venv" / "Scripts" / "python.exe"


def record_gate_b():
    print("Running Gate B tests under .acceptance_venv...")
    cmd = [
        str(VENV_PYTHON), "-m", "pytest",
        "tests/test_gate_b_kernel_render.py",
        "tests/test_gate_b_engine_resumption.py",
        "tests/test_gate_b_evidence_bundle.py",
        "-v"
    ]
    proc = subprocess.run(cmd, capture_output=True, text=True, cwd=str(BASE_DIR))
    print(proc.stdout)
    if proc.stderr:
        print(proc.stderr, file=sys.stderr)

    report = {
        "python_executable": str(VENV_PYTHON),
        "test_command": " ".join(cmd),
        "exit_code": proc.returncode,
        "status": "PASS" if proc.returncode == 0 else "FAIL",
        "tests_output": proc.stdout,
        "artifacts_generated": {
            "kernel_rendered_pdf": str(EVIDENCE_DIR / "gate_b_artifacts" / "kernel_rendered_dossier.pdf"),
            "pdf_exists": (EVIDENCE_DIR / "gate_b_artifacts" / "kernel_rendered_dossier.pdf").exists()
        }
    }

    report_file = EVIDENCE_DIR / "gate_b_report.json"
    report_file.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(f"Gate B evidence report written to: {report_file}")

    if proc.returncode != 0:
        sys.exit(proc.returncode)


if __name__ == "__main__":
    record_gate_b()
