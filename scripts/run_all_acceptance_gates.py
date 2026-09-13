import subprocess, sys, json, datetime
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
EVIDENCE_DIR = BASE_DIR / 'acceptance' / 'evidence'
EVIDENCE_DIR.mkdir(parents=True, exist_ok=True)
SUMMARY_REPORT_FILE = EVIDENCE_DIR / 'full_acceptance_report.json'

SUITES = [
    ("Gate A: Public PyPI Installation & Wheel Integrity", ["scripts/verify_clean_install.py"]),
    ("Gate B: Public Artifact Engine & ProDocuX Kernel Isolated Invariants", ["scripts/run_gate_b_suite.py"]),
    ("Gate C: Causal Chain Integration (Engine Plans & Kernel Evidence Bundles)", ["scripts/run_gate_c_suite.py"]),
    ("Gate D & E: DES Simulation Physics & Single Source Accounting", ["scripts/run_gate_d_e_suite.py"]),
]

def main():
    overall_start = datetime.datetime.now(datetime.timezone.utc)
    suite_results = []
    overall_exit_code = 0

    print("=" * 80)
    print("PDX-ROADSTAR FULL ACCEPTANCE BATTERY (GATES A - E)")
    print(f"Timestamp: {overall_start.isoformat()}")
    print("=" * 80)

    for name, script_args in SUITES:
        cmd = [sys.executable] + script_args
        print(f"\n[RUNNING] {name} -> {' '.join(cmd)}")
        proc = subprocess.run(cmd, cwd=str(BASE_DIR), capture_output=True, text=True)
        print(proc.stdout)
        if proc.stderr:
            print(f"[STDERR]: {proc.stderr}")

        success = proc.returncode == 0
        if not success:
            overall_exit_code = proc.returncode

        suite_results.append({
            "name": name,
            "command": " ".join(cmd),
            "exit_code": proc.returncode,
            "status": "PASSED" if success else "FAILED",
            "stdout": proc.stdout,
            "stderr": proc.stderr
        })

    blockers = json.loads((BASE_DIR / "acceptance" / "capability_status.json").read_text(encoding="utf-8"))["blocked_requirements"]
    tests_exit_code = overall_exit_code
    if blockers and overall_exit_code == 0:
        overall_exit_code = 2
    overall_end = datetime.datetime.now(datetime.timezone.utc)
    summary_report = {
        "generated_at": overall_end.isoformat(),
        "duration_seconds": (overall_end - overall_start).total_seconds(),
        "overall_status": "FAILED" if tests_exit_code else ("BLOCKED" if blockers else "PASSED"),
        "tests_status": "FAILED" if tests_exit_code else "PASSED",
        "blocked_requirements": blockers,
        "overall_exit_code": overall_exit_code,
        "suites": suite_results
    }

    SUMMARY_REPORT_FILE.write_text(json.dumps(summary_report, indent=2), encoding="utf-8")
    print("=" * 80)
    print(f"SUMMARY: Overall Status: {summary_report['overall_status']} (Exit Code {overall_exit_code})")
    print(f"Report written to: {SUMMARY_REPORT_FILE}")
    print("=" * 80)
    sys.exit(overall_exit_code)

if __name__ == "__main__":
    main()
