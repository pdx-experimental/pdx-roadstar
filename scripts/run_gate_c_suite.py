import subprocess, sys, json, datetime, re
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
EVIDENCE_DIR = BASE_DIR / 'acceptance' / 'evidence'
EVIDENCE_DIR.mkdir(parents=True, exist_ok=True)
REPORT_FILE = EVIDENCE_DIR / 'gate_c_report.json'

def run():
    test_files = [
        'tests/test_gate_c_causal_chain.py',
        'tests/test_causal_regression_failures.py'
    ]
    cmd = [sys.executable, '-m', 'pytest'] + test_files + ['-v', '--tb=short']
    print(f'[RUNNER] Executing: {" ".join(cmd)}')
    proc = subprocess.run(cmd, cwd=str(BASE_DIR), capture_output=True, text=True)

    test_regex = re.compile(r"^(tests/[^\s:]+::\S+)\s+(PASSED|FAILED|SKIPPED)", re.MULTILINE)
    matches = test_regex.findall(proc.stdout)
    tests_data = [{'nodeid': m[0], 'outcome': m[1]} for m in matches]

    report = {
        'generated_at': datetime.datetime.now(datetime.timezone.utc).isoformat(),
        'command': ' '.join(cmd),
        'exit_code': proc.returncode,
        'total_tests': len(tests_data),
        'passed': sum(1 for t in tests_data if t['outcome'] == 'PASSED'),
        'failed': sum(1 for t in tests_data if t['outcome'] == 'FAILED'),
        'tests': tests_data,
        'raw_stdout': proc.stdout,
        'raw_stderr': proc.stderr
    }

    REPORT_FILE.write_text(json.dumps(report, indent=2), encoding='utf-8')
    p_count = report['passed']
    t_count = report['total_tests']
    print(f'[RUNNER] Exit code: {proc.returncode}, Passed: {p_count}/{t_count}')
    sys.exit(proc.returncode)

if __name__ == '__main__':
    run()
