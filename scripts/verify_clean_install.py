"""Verifies that installed packages in site-packages match the external verified PyPI wheel files directly.
Exits with non-zero code if ANY check fails.
"""
import os
import sys
import json
import zipfile
import hashlib
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
VENV_DIR = BASE_DIR / ".acceptance_venv"
CACHE_DIR = BASE_DIR / ".wheel_cache"
EVIDENCE_DIR = BASE_DIR / "acceptance" / "evidence"

EXPECTED_WHEELS = {
    "prodocux": {
        "filename": "prodocux-0.3.0rc4-py3-none-any.whl",
        "sha256": "6c6801318f4b649877ca680d4897bbe6917def60f888073ec6d5e20f916c3d47",
        "top_levels": ["prodocux_kernel", "api", "skills"]
    },
    "pdx-artifact-engine": {
        "filename": "pdx_artifact_engine-0.3.0a5-py3-none-any.whl",
        "sha256": "75e7a180d0f7f4638e276612a336e26d0595aa15092a8ab538a0af68276d4854",
        "top_levels": ["pdx_artifact_engine", "pdx_artifact_core", "pdx_adapter_prodocux"]
    }
}


def verify():
    exec_path = str(Path(sys.executable).resolve()).lower()
    in_venv = (
        sys.prefix != sys.base_prefix or
        exec_path.startswith(str(VENV_DIR.resolve()).lower()) or
        exec_path.startswith(str((BASE_DIR / ".venv").resolve()).lower())
    )
    report = {
        "python_executable": sys.executable,
        "is_acceptance_venv": in_venv,
        "packages": {},
        "overall_status": "PASS"
    }

    if not in_venv:
        print(f"FATAL: Running with non-virtualenv system Python: {sys.executable}", file=sys.stderr)
        sys.exit(1)

    import importlib.metadata
    site_packages = Path(importlib.metadata.distribution("prodocux").locate_file("")).resolve()
    report["site_packages_dir"] = str(site_packages)

    for pkg_name, info in EXPECTED_WHEELS.items():
        wheel_path = CACHE_DIR / info["filename"]
        if not wheel_path.exists():
            print(f"FATAL: External verified wheel not found: {wheel_path}", file=sys.stderr)
            sys.exit(1)

        # 1. Verify external wheel SHA-256 against official PyPI digest
        wheel_bytes = wheel_path.read_bytes()
        computed_wheel_sha = hashlib.sha256(wheel_bytes).hexdigest()
        if computed_wheel_sha != info["sha256"]:
            print(f"FATAL: Wheel SHA-256 mismatch for {info['filename']}! Expected {info['sha256']}, got {computed_wheel_sha}", file=sys.stderr)
            sys.exit(1)

        # 2. Check installed package distribution metadata
        dist = importlib.metadata.distribution(pkg_name)
        
        # Check for editable hooks or local paths
        for f in (dist.files or []):
            if "direct_url.json" in str(f):
                content = json.loads(dist.read_text("direct_url.json") or "{}")
                if content.get("dir_info", {}).get("editable"):
                    print(f"FATAL: Package {pkg_name} is marked EDITABLE!", file=sys.stderr)
                    sys.exit(1)

        verified_files = 0
        mismatched_files = []
        missing_files = []
        extra_files = []

        # 3. Compare site-packages files directly against wheel archive content
        with zipfile.ZipFile(wheel_path) as zf:
            wheel_namelist = set(zf.namelist())
            for name in sorted(wheel_namelist):
                # Skip metadata records generated during install
                if name.endswith(".dist-info/RECORD") or name.endswith(".dist-info/INSTALLER"):
                    continue

                target_file = site_packages / name
                if not target_file.exists():
                    missing_files.append(name)
                    continue

                wheel_content = zf.read(name)
                installed_content = target_file.read_bytes()

                wheel_sha = hashlib.sha256(wheel_content).hexdigest()
                installed_sha = hashlib.sha256(installed_content).hexdigest()

                if wheel_sha != installed_sha:
                    mismatched_files.append({
                        "file": name,
                        "wheel_sha256": wheel_sha,
                        "installed_sha256": installed_sha
                    })
                else:
                    verified_files += 1

            # 4. Check for unauthorized extra files in package directories
            for top_level in info["top_levels"]:
                top_dir = site_packages / top_level
                if top_dir.exists():
                    for installed_path in top_dir.rglob("*.py"):
                        rel_name = installed_path.relative_to(site_packages).as_posix()
                        if rel_name not in wheel_namelist:
                            extra_files.append(rel_name)

        status = "PASS" if not missing_files and not mismatched_files and not extra_files else "FAIL"
        if status != "PASS":
            report["overall_status"] = "FAIL"

        report["packages"][pkg_name] = {
            "version": dist.version,
            "wheel_verified_files": verified_files,
            "missing_files": missing_files,
            "mismatched_files": mismatched_files,
            "extra_files": extra_files,
            "status": status
        }

    # 5. Import module origins check
    import prodocux_kernel
    import pdx_artifact_core
    import pdx_artifact_engine

    report["module_origins"] = {
        "prodocux_kernel": str(Path(prodocux_kernel.__file__).resolve()),
        "pdx_artifact_core": str(Path(pdx_artifact_core.__file__).resolve()),
        "pdx_artifact_engine": str(Path(pdx_artifact_engine.__file__).resolve())
    }

    # Verify each module is inside the verified site-packages
    for mod_name, mod_path in report["module_origins"].items():
        if not mod_path.lower().startswith(str(site_packages).lower()):
            print(f"FATAL: Module {mod_name} origin {mod_path} is outside site-packages {site_packages}!", file=sys.stderr)
            sys.exit(1)

    # 6. Run pip check programmatically
    import subprocess
    check_proc = subprocess.run([sys.executable, "-m", "pip", "check"], capture_output=True, text=True)
    report["pip_check_exit_code"] = check_proc.returncode
    report["pip_check_output"] = check_proc.stdout.strip() or check_proc.stderr.strip()
    if check_proc.returncode != 0:
        print(f"FATAL: pip check failed:\n{report['pip_check_output']}", file=sys.stderr)
        report["overall_status"] = "FAIL"

    EVIDENCE_DIR.mkdir(parents=True, exist_ok=True)
    report_file = EVIDENCE_DIR / "external_wheel_integrity_report.json"
    report_file.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(f"External wheel integrity report written to: {report_file}")
    print(json.dumps(report, indent=2))

    if report["overall_status"] != "PASS":
        print("FATAL: Package verification failed!", file=sys.stderr)
        sys.exit(1)

    print("\n[SUCCESS] All packages verified 100% identical to external PyPI wheels.\n")


if __name__ == "__main__":
    verify()
