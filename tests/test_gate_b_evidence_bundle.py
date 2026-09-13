"""Gate B Test: Verifies end-to-end evidence chain from verified document bytes to parsed fields and Kernel audit.
Proves: Verified PDF bytes -> Genuine Kernel intake.pdf.extract_pdf_bytes -> Kernel verify_evidence_bundle rules.
Includes both positive flow and negative rejection checks.
"""
import hashlib
from pathlib import Path
import pytest
import prodocux_kernel
import prodocux_kernel.rendering.service as rs
from prodocux_kernel.rendering.ports import ArtifactSinkPort
import prodocux_kernel.intake.pdf as intake_pdf
import prodocux_kernel.verification.evidence as ev
from prodocux_kernel.artifacts import resolve_opaque_artifact, OpaqueArtifactResolver

BASE_DIR = Path(__file__).resolve().parent.parent
EVIDENCE_DIR = BASE_DIR / "acceptance" / "evidence" / "gate_b_artifacts"
EVIDENCE_DIR.mkdir(parents=True, exist_ok=True)


class LocalResolver(OpaqueArtifactResolver):
    def __init__(self, storage: dict[str, bytes]):
        self.storage = storage

    def resolve(self, uri: str) -> bytes:
        return self.storage[uri]


class BufferSink(ArtifactSinkPort):
    def __init__(self):
        self.payload = b""
        self.sha256 = ""

    def create_if_absent(self, *, output_name: str, media_type: str, payload: bytes, sha256: str):
        self.payload = payload
        self.sha256 = sha256
        return {"status": "created", "output_name": output_name, "sha256": sha256}


def run_pipeline_for_dossier(
    *,
    arrival_iso: str,
    departure_iso: str,
    dwell_hours: float,
    request_id: str
) -> dict:
    """Helper that runs the complete causal chain:
    1. Kernel execute_render_artifact -> PDF bytes
    2. Kernel resolve_opaque_artifact -> verifies integrity
    3. Kernel intake.pdf.extract_pdf_bytes -> extracts page text
    4. Domain parses field values from Kernel-extracted text
    5. Kernel verify_evidence_bundle -> evaluates deterministic checks
    """
    sink = BufferSink()
    render_req = {
        "schema_version": "prodocux_render_request_v1",
        "request_id": f"req-render-{request_id}",
        "target_format": "pdf",
        "output": {"output_name": f"{request_id}.pdf", "delivery_mode": "artifact"},
        "content": {
            "schema_version": "prodocux_content_blocks_v1",
            "blocks": [
                {
                    "id": "hdr",
                    "type": "heading",
                    "level": 1,
                    "text": "CARRIER TELEMATICS DOCK DWELL LOG"
                },
                {
                    "id": "body",
                    "type": "paragraphs",
                    "paragraphs": [
                        "TRIP: TRIP-622819",
                        f"ARRIVAL_TIMESTAMP: {arrival_iso}",
                        f"DEPARTURE_TIMESTAMP: {departure_iso}",
                        f"CLAIMED_DWELL_HOURS: {dwell_hours:.2f}"
                    ]
                }
            ]
        }
    }
    code, res = rs.execute_render_artifact(render_req, sink=sink)
    assert code == 200, f"Render failed: {res}"
    pdf_bytes = sink.payload
    pdf_sha256 = sink.sha256
    assert pdf_sha256 == hashlib.sha256(pdf_bytes).hexdigest()

    # Step 2: Resolve & verify opaque artifact
    doc_uri = f"artifact://roadstar/runs/{request_id}.pdf"
    resolver = LocalResolver({doc_uri: pdf_bytes})
    artifact_identity = {
        "schema_version": "prodocux_opaque_artifact_v1",
        "artifact_id": f"art-{request_id}",
        "uri": doc_uri,
        "media_type": "application/pdf",
        "size_bytes": len(pdf_bytes),
        "sha256": pdf_sha256
    }
    verified_bytes = resolve_opaque_artifact(artifact_identity, resolver, max_bytes=10 * 1024 * 1024)
    assert verified_bytes == pdf_bytes

    # Step 3: Extract text using genuine public Kernel intake.pdf
    pages, truncated = intake_pdf.extract_pdf_bytes(verified_bytes, filename=f"{request_id}.pdf")
    assert len(pages) >= 1
    assert not truncated
    extracted_text = pages[0]["text"]

    # Step 4: Parse field values from Kernel-extracted text
    parsed_fields = {}
    for line in extracted_text.splitlines():
        line = line.strip()
        if ":" in line:
            k, v = line.split(":", 1)
            parsed_fields[k.strip()] = v.strip()

    assert "ARRIVAL_TIMESTAMP" in parsed_fields
    assert "DEPARTURE_TIMESTAMP" in parsed_fields
    assert "CLAIMED_DWELL_HOURS" in parsed_fields

    # Step 5: Construct Evidence Bundle referencing Kernel extraction identity
    req = {
        "schema_version": "prodocux_evidence_bundle_request_v1",
        "request_id": request_id,
        "rule_set": {"id": "roadstar.carrier_audit_policy", "version": "1.0", "sha256": "0" * 64},
        "documents": [
            {
                "document_id": "doc-telematics-pdf",
                "media_type": "application/pdf",
                "source_sha256": pdf_sha256
            }
        ],
        "evidence": [
            {
                "evidence_id": "ev-arrival",
                "document_id": "doc-telematics-pdf",
                "field_name": "geofence_arrival_timestamp",
                "value_type": "date",
                "value": parsed_fields["ARRIVAL_TIMESTAMP"],
                "confidence": 1.0,
                "source_reference": {
                    "schema_version": "prodocux_source_reference_v1",
                    "media_type": "application/pdf",
                    "source_sha256": pdf_sha256,
                    "locator": {"kind": "pdf_page", "page": 1, "bbox": None},
                    "extraction": {
                        "method": "native_text",
                        "extractor_id": "prodocux_kernel.intake.pdf",
                        "extractor_version": prodocux_kernel.__version__
                    },
                    "truncated": False
                }
            },
            {
                "evidence_id": "ev-departure",
                "document_id": "doc-telematics-pdf",
                "field_name": "geofence_departure_timestamp",
                "value_type": "date",
                "value": parsed_fields["DEPARTURE_TIMESTAMP"],
                "confidence": 1.0,
                "source_reference": {
                    "schema_version": "prodocux_source_reference_v1",
                    "media_type": "application/pdf",
                    "source_sha256": pdf_sha256,
                    "locator": {"kind": "pdf_page", "page": 1, "bbox": None},
                    "extraction": {
                        "method": "native_text",
                        "extractor_id": "prodocux_kernel.intake.pdf",
                        "extractor_version": prodocux_kernel.__version__
                    },
                    "truncated": False
                }
            },
            {
                "evidence_id": "ev-dwell",
                "document_id": "doc-telematics-pdf",
                "field_name": "total_dwell_hours",
                "value_type": "number",
                "value": float(parsed_fields["CLAIMED_DWELL_HOURS"]),
                "confidence": 1.0,
                "source_reference": {
                    "schema_version": "prodocux_source_reference_v1",
                    "media_type": "application/pdf",
                    "source_sha256": pdf_sha256,
                    "locator": {"kind": "pdf_page", "page": 1, "bbox": None},
                    "extraction": {
                        "method": "native_text",
                        "extractor_id": "prodocux_kernel.intake.pdf",
                        "extractor_version": prodocux_kernel.__version__
                    },
                    "truncated": False
                }
            }
        ],
        "checks": [
            {
                "check_id": "chk-chronology",
                "kind": "date_order",
                "evidence_ids": ["ev-arrival", "ev-departure"]
            },
            {
                "check_id": "chk-free-time-threshold",
                "kind": "numeric_range",
                "evidence_ids": ["ev-dwell"],
                "minimum": 2.0,
                "minimum_inclusive": False
            }
        ]
    }
    return ev.verify_evidence_bundle(req)


def test_kernel_evidence_bundle_positive_connected():
    """Positive test: Chronology is valid (arrival < departure) and dwell > 2.0 hrs."""
    audit_res = run_pipeline_for_dossier(
        arrival_iso="2026-08-14T08:30:00+00:00",
        departure_iso="2026-08-14T11:45:00+00:00",
        dwell_hours=3.25,
        request_id="audit-det-positive-001"
    )
    assert audit_res["status"] == "pass"
    assert audit_res["results"][0]["status"] == "pass"
    assert audit_res["results"][0]["reason_codes"] == ["DATE_ORDER_VALID"]
    assert audit_res["results"][1]["status"] == "pass"
    assert audit_res["results"][1]["reason_codes"] == ["VALUE_WITHIN_RANGE"]
    print(f"\n[PASS] Connected Evidence Positive Audit Passed: {audit_res['canonical_request_sha256']}")


def test_kernel_evidence_bundle_negative_inverted_chronology_fails():
    """Negative test: Chronology inverted (departure is before arrival).
    Kernel must reject with DATE_ORDER_INVALID and overall fail.
    """
    audit_res = run_pipeline_for_dossier(
        arrival_iso="2026-08-14T11:45:00+00:00",
        departure_iso="2026-08-14T08:30:00+00:00",
        dwell_hours=3.25,
        request_id="audit-det-negative-chronology"
    )
    assert audit_res["status"] == "fail"
    chk_chronology = next(r for r in audit_res["results"] if r["check_id"] == "chk-chronology")
    assert chk_chronology["status"] == "fail"
    assert "DATE_ORDER_INVALID" in chk_chronology["reason_codes"]
    print(f"\n[PASS] Negative Chronology Rejection Verified: {chk_chronology['reason_codes']}")


def test_kernel_evidence_bundle_negative_below_free_time_fails():
    """Negative test: Dwell hours (1.5 hrs) <= free time threshold (2.0 hrs).
    Kernel must reject with VALUE_BELOW_MINIMUM and overall fail.
    """
    audit_res = run_pipeline_for_dossier(
        arrival_iso="2026-08-14T08:30:00+00:00",
        departure_iso="2026-08-14T10:00:00+00:00",
        dwell_hours=1.5,
        request_id="audit-det-negative-freetime"
    )
    assert audit_res["status"] == "fail"
    chk_dwell = next(r for r in audit_res["results"] if r["check_id"] == "chk-free-time-threshold")
    assert chk_dwell["status"] == "fail"
    assert "VALUE_BELOW_MINIMUM" in chk_dwell["reason_codes"]
    print(f"\n[PASS] Negative Free Time Rejection Verified: {chk_dwell['reason_codes']}")

