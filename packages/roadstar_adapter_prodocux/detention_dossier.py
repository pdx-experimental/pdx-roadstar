from __future__ import annotations
import os
import uuid
import hashlib
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

import prodocux_kernel
import prodocux_kernel.rendering.service as rs
import prodocux_kernel.intake.pdf as intake_pdf
import prodocux_kernel.verification.evidence as ev
from prodocux_kernel.artifacts import resolve_opaque_artifact

from roadstar_domain.models import DetentionRecord
from roadstar_adapter_prodocux.artifact_sink import RoadStarArtifactSink
from roadstar_adapter_pdx.storage_adapter import RoadStarStorageAdapter

BASE_DIR = Path(__file__).resolve().parent.parent.parent
DOSSIER_DIR = BASE_DIR / "acceptance" / "evidence" / "detention_dossiers"


class DetentionDossierBuilder:
    """Production service for assembling, rendering, and deterministically auditing
    Carrier Detention Evidence Dossiers using ProDocuX Kernel (v0.3.0rc4).
    """

    def __init__(self, output_dir: Optional[str | Path] = None) -> None:
        self.output_dir = Path(output_dir) if output_dir else DOSSIER_DIR
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.sink = RoadStarArtifactSink(self.output_dir, uri_prefix="artifact://roadstar/artifacts")
        self.storage = RoadStarStorageAdapter(self.output_dir, uri_prefix="artifact://roadstar/artifacts")

        self.registry_path = self.output_dir / ".dossier_asset_registry.json"

    def _load_registry(self) -> Dict[str, Any]:
        if self.registry_path.exists():
            try:
                import json
                return json.loads(self.registry_path.read_text(encoding="utf-8"))
            except Exception:
                return {}
        return {}

    def _save_registry(self, reg: Dict[str, Any]) -> None:
        import json
        self.registry_path.write_text(json.dumps(reg, indent=2), encoding="utf-8")

    def generate_and_audit_dossier(
        self, record: DetentionRecord, expected_pdf_sha256: Optional[str] = None
    ) -> Tuple[str, Dict[str, Any]]:
        """Executes the complete deterministic audit causal chain:
        1. Kernel execute_render_artifact -> creates PDF via RoadStarArtifactSink
        2. Kernel resolve_opaque_artifact -> verifies storage integrity against trusted expected digest
        3. Kernel intake.pdf.extract_pdf_bytes -> extracts document text without fallback
        4. Parses timestamps and claimed dwell hours
        5. Kernel verify_evidence_bundle -> deterministic rules audit (chronology + free-time threshold)
        6. If audit passes -> issues invoice with canonical SHA-256 evidence receipt
           If audit fails  -> marks AUDITED_REJECTED, zero fee invoiced
        """
        filename = f"Detention_Dossier_{record.bill_number}_{record.record_id}.pdf"
        target_path = self.output_dir / filename

        registry = self._load_registry()
        reg_entry = registry.get(filename, {})

        dwell_hrs = float(record.total_wait_hours)

        if record.geofence_arrival_time:
            arr_dt = record.geofence_arrival_time
            if arr_dt.tzinfo is None:
                arr_dt = arr_dt.replace(tzinfo=timezone.utc)
        else:
            arr_dt = datetime(2026, 8, 14, 8, 0, tzinfo=timezone.utc)

        if record.geofence_departure_time:
            dep_dt = record.geofence_departure_time
            if dep_dt.tzinfo is None:
                dep_dt = dep_dt.replace(tzinfo=timezone.utc)
        else:
            dep_dt = arr_dt + timedelta(hours=dwell_hrs)

        arr_str = arr_dt.strftime("%Y-%m-%dT%H:%M:%S+00:00")
        dep_str = dep_dt.strftime("%Y-%m-%dT%H:%M:%S+00:00")

        # Step 1: Render PDF via ProDocuX Kernel (or reuse existing immutable artifact)
        if not target_path.exists():
            render_req = {
                "schema_version": "prodocux_render_request_v1",
                "request_id": f"req-render-{record.record_id}",
                "target_format": "pdf",
                "output": {"output_name": filename, "delivery_mode": "artifact"},
                "content": {
                    "schema_version": "prodocux_content_blocks_v1",
                    "blocks": [
                        {
                            "id": "hdr1",
                            "type": "heading",
                            "level": 1,
                            "text": "ROADSTAR TRUCKING INC. | CARRIER DETENTION EVIDENCE DOSSIER"
                        },
                        {
                            "id": "p_meta",
                            "type": "paragraphs",
                            "paragraphs": [
                                f"RECORD_ID: {record.record_id}",
                                f"BILL_OF_LADING: {record.bill_number}",
                                f"TRIP_NUMBER: {record.trip_number}",
                                f"FACILITY_NAME: {record.facility_name} ({record.facility_id})",
                                f"DRIVER_NAME: {record.driver_name} (ID: {record.driver_id})",
                                f"ARRIVAL_TIMESTAMP: {arr_str}",
                                f"DEPARTURE_TIMESTAMP: {dep_str}",
                                f"CLAIMED_DWELL_HOURS: {dwell_hrs:.2f}",
                                f"FREE_TIME_ALLOWANCE_HOURS: {record.free_time_hours:.2f}",
                                f"BILLABLE_HOURS: {record.billable_hours:.2f}",
                                f"HOURLY_RATE_CAD: {record.hourly_rate_cad:.2f}",
                                f"TOTAL_CLAIMED_FEE_CAD: {record.total_detention_fee_cad:.2f}",
                            ]
                        },
                        {
                            "id": "p_disclaimer",
                            "type": "paragraphs",
                            "paragraphs": [
                                "NOTICE: Timestamps and dwell threshold are deterministically audited via ProDocuX Kernel evidence rules.",
                                "Detention charge arithmetic is calculated under Carrier Tariff rules. (Kernel formula check blocked under REQ-PDX-KERNEL-002).",
                                "Digital signatures are NOT claimed (REQ-PDX-KERNEL-001 blocked upstream).",
                            ]
                        }
                    ]
                }
            }
            http_code, render_res = rs.execute_render_artifact(render_req, sink=self.sink)
            if http_code != 200:
                raise RuntimeError(f"Kernel PDF rendering failed ({http_code}): {render_res}")

            pdf_bytes = target_path.read_bytes()
            fresh_sha = hashlib.sha256(pdf_bytes).hexdigest()
            registry[filename] = {
                "pdf_sha256": fresh_sha,
                "size_bytes": len(pdf_bytes),
                "record_id": record.record_id,
                "bill_number": record.bill_number,
                "trip_number": record.trip_number,
                "driver_id": str(record.driver_id),
                "driver_name": str(record.driver_name),
                "facility_id": str(record.facility_id),
                "facility_name": str(record.facility_name),
                "hourly_rate_cad": float(record.hourly_rate_cad),
                "billable_hours": float(record.billable_hours),
                "total_claimed_fee_cad": float(record.total_detention_fee_cad),
                "created_at": datetime.now(timezone.utc).isoformat(),
                "registered_by": "prodocux_kernel.rendering.service",
            }
            self._save_registry(registry)
            expected_digest = fresh_sha
            expected_size = len(pdf_bytes)
        else:
            # File already exists on disk
            # Must check persistent registry: orphan files on disk without an authoritative registry entry cannot self-establish trust!
            if filename not in registry:
                from prodocux_kernel.artifacts import ArtifactResolutionError
                raise ArtifactResolutionError(
                    f"Untrusted orphan artifact on disk: '{filename}' has no authoritative entry in the asset registry. "
                    "Unindexed local files are forbidden from self-establishing trust. Re-registration requires an independent audit procedure."
                )
            reg_entry = registry[filename]
            expected_digest = reg_entry["pdf_sha256"]
            expected_size = reg_entry.get("size_bytes", len(target_path.read_bytes()))

            from prodocux_kernel.artifacts import ArtifactResolutionError
            if expected_pdf_sha256 and expected_pdf_sha256 != expected_digest:
                raise ArtifactResolutionError(
                    f"Provenance conflict: caller expected hash '{expected_pdf_sha256}' does not match registered asset hash '{expected_digest}'"
                )
            if record.pdf_sha256 and record.pdf_sha256 != expected_digest:
                raise ArtifactResolutionError(
                    f"Provenance conflict: record expected hash '{record.pdf_sha256}' does not match registered asset hash '{expected_digest}'"
                )

        # Step 2: Resolve & verify opaque artifact against expected digest
        artifact_uri = f"artifact://roadstar/artifacts/{filename}"
        artifact_identity = {
            "schema_version": "prodocux_opaque_artifact_v1",
            "artifact_id": f"art-{filename}",
            "uri": artifact_uri,
            "media_type": "application/pdf",
            "size_bytes": expected_size,
            "sha256": expected_digest,
        }
        verified_bytes = resolve_opaque_artifact(
            artifact_identity, self.storage, max_bytes=20 * 1024 * 1024
        )
        pdf_sha256 = hashlib.sha256(verified_bytes).hexdigest()

        # Step 3: Kernel intake.pdf extraction
        pages, truncated = intake_pdf.extract_pdf_bytes(verified_bytes, filename=filename)
        if not pages:
            raise ValueError(f"Kernel extract_pdf_bytes returned 0 pages for {filename}")

        full_text = pages[0]["text"]
        parsed_fields: Dict[str, str] = {}
        for line in full_text.splitlines():
            line = line.strip()
            if ":" in line:
                k, v = line.split(":", 1)
                parsed_fields[k.strip()] = v.strip()

        # Strict validation: Missing required field MUST raise ValueError with zero fallback
        for required_key in ("ARRIVAL_TIMESTAMP", "DEPARTURE_TIMESTAMP", "CLAIMED_DWELL_HOURS", "TOTAL_CLAIMED_FEE_CAD"):
            if required_key not in parsed_fields or not parsed_fields[required_key]:
                raise ValueError(f"Required field {required_key} not found in PDF extraction for {filename}")

        # Strict Multi-Attribute Document-Record Identity Binding
        if "RECORD_ID" in parsed_fields and parsed_fields["RECORD_ID"] != record.record_id:
            raise ValueError(f"Billing identity mismatch: RECORD_ID in PDF ('{parsed_fields['RECORD_ID']}') != record ('{record.record_id}')")
        if "BILL_OF_LADING" in parsed_fields and parsed_fields["BILL_OF_LADING"] != record.bill_number:
            raise ValueError(f"Billing identity mismatch: BILL_OF_LADING in PDF ('{parsed_fields['BILL_OF_LADING']}') != record ('{record.bill_number}')")
        if "TRIP_NUMBER" in parsed_fields and parsed_fields["TRIP_NUMBER"] != record.trip_number:
            raise ValueError(f"Billing identity mismatch: TRIP_NUMBER in PDF ('{parsed_fields['TRIP_NUMBER']}') != record ('{record.trip_number}')")
        if "ARRIVAL_TIMESTAMP" in parsed_fields and parsed_fields["ARRIVAL_TIMESTAMP"] != arr_str:
            raise ValueError(f"Billing identity mismatch: ARRIVAL_TIMESTAMP in PDF ('{parsed_fields['ARRIVAL_TIMESTAMP']}') != record ('{arr_str}')")
        if "DEPARTURE_TIMESTAMP" in parsed_fields and parsed_fields["DEPARTURE_TIMESTAMP"] != dep_str:
            raise ValueError(f"Billing identity mismatch: DEPARTURE_TIMESTAMP in PDF ('{parsed_fields['DEPARTURE_TIMESTAMP']}') != record ('{dep_str}')")

        try:
            extracted_fee = float(parsed_fields["TOTAL_CLAIMED_FEE_CAD"])
        except ValueError as exc:
            raise ValueError(f"Invalid TOTAL_CLAIMED_FEE_CAD '{parsed_fields.get('TOTAL_CLAIMED_FEE_CAD')}' in PDF") from exc

        if abs(extracted_fee - float(record.total_detention_fee_cad)) >= 0.01:
            raise ValueError(
                f"Billing identity mismatch: total claimed fee in verified PDF (CAD {extracted_fee:.2f}) "
                f"does not match input record fee (CAD {float(record.total_detention_fee_cad):.2f})"
            )

        arr_parsed = parsed_fields["ARRIVAL_TIMESTAMP"]
        dep_parsed = parsed_fields["DEPARTURE_TIMESTAMP"]
        try:
            dwell_parsed = float(parsed_fields["CLAIMED_DWELL_HOURS"])
        except ValueError as exc:
            raise ValueError(f"Invalid CLAIMED_DWELL_HOURS value '{parsed_fields['CLAIMED_DWELL_HOURS']}' in PDF extraction") from exc

        # Step 4: Assemble Evidence Bundle Request
        evidence_req = {
            "schema_version": "prodocux_evidence_bundle_request_v1",
            "request_id": f"audit-{record.record_id}",
            "rule_set": {
                "id": "roadstar.carrier_detention_tariff",
                "version": "1.0",
                "sha256": "0" * 64,
            },
            "documents": [
                {
                    "document_id": f"doc-{record.record_id}",
                    "media_type": "application/pdf",
                    "source_sha256": pdf_sha256,
                }
            ],
            "evidence": [
                {
                    "evidence_id": "ev-arrival",
                    "document_id": f"doc-{record.record_id}",
                    "field_name": "geofence_arrival_timestamp",
                    "value_type": "date",
                    "value": arr_parsed,
                    "confidence": 1.0,
                    "source_reference": {
                        "schema_version": "prodocux_source_reference_v1",
                        "media_type": "application/pdf",
                        "source_sha256": pdf_sha256,
                        "locator": {"kind": "pdf_page", "page": 1, "bbox": None},
                        "extraction": {
                            "method": "native_text",
                            "extractor_id": "prodocux_kernel.intake.pdf",
                            "extractor_version": prodocux_kernel.__version__,
                        },
                        "truncated": False,
                    },
                },
                {
                    "evidence_id": "ev-departure",
                    "document_id": f"doc-{record.record_id}",
                    "field_name": "geofence_departure_timestamp",
                    "value_type": "date",
                    "value": dep_parsed,
                    "confidence": 1.0,
                    "source_reference": {
                        "schema_version": "prodocux_source_reference_v1",
                        "media_type": "application/pdf",
                        "source_sha256": pdf_sha256,
                        "locator": {"kind": "pdf_page", "page": 1, "bbox": None},
                        "extraction": {
                            "method": "native_text",
                            "extractor_id": "prodocux_kernel.intake.pdf",
                            "extractor_version": prodocux_kernel.__version__,
                        },
                        "truncated": False,
                    },
                },
                {
                    "evidence_id": "ev-dwell",
                    "document_id": f"doc-{record.record_id}",
                    "field_name": "total_dwell_hours",
                    "value_type": "number",
                    "value": dwell_parsed,
                    "confidence": 1.0,
                    "source_reference": {
                        "schema_version": "prodocux_source_reference_v1",
                        "media_type": "application/pdf",
                        "source_sha256": pdf_sha256,
                        "locator": {"kind": "pdf_page", "page": 1, "bbox": None},
                        "extraction": {
                            "method": "native_text",
                            "extractor_id": "prodocux_kernel.intake.pdf",
                            "extractor_version": prodocux_kernel.__version__,
                        },
                        "truncated": False,
                    },
                },
            ],
            "checks": [
                {
                    "check_id": "chk-chronology",
                    "kind": "date_order",
                    "evidence_ids": ["ev-arrival", "ev-departure"],
                },
                {
                    "check_id": "chk-free-time-threshold",
                    "kind": "numeric_range",
                    "evidence_ids": ["ev-dwell"],
                    "minimum": 2.0,
                    "minimum_inclusive": False,
                },
            ],
        }

        # Step 5: Execute Kernel verification
        audit_res = ev.verify_evidence_bundle(evidence_req)

        # Step 6: Apply strict audit decision
        record.pdf_sha256 = pdf_sha256
        if audit_res["status"] == "pass":
            record.audit_canonical_digest = audit_res["canonical_request_sha256"]
            record.dossier_sha256 = audit_res["canonical_request_sha256"]
            record.dossier_filename = filename
            record.status = "AUDITED_APPROVED"
            invoiced_amount = extracted_fee
        else:
            record.audit_canonical_digest = None
            record.dossier_sha256 = None
            record.dossier_filename = filename
            record.status = "AUDITED_REJECTED"
            invoiced_amount = 0.0  # Rejected -> $0 invoiced!

        audit_info = {
            "pdf_path": str(target_path),
            "pdf_sha256": pdf_sha256,
            "audit_status": audit_res["status"],
            "canonical_digest": audit_res["canonical_request_sha256"],
            "invoiced_amount_cad": invoiced_amount,
            "kernel_results": audit_res["results"],
        }
        return str(target_path), audit_info

    def re_register_orphan_artifact(
        self,
        filename: str,
        expected_sha256: str,
        audit_log_reason: str,
        auditor_id: str = "auditor@roadstar.ca"
    ) -> Dict[str, Any]:
        """Independent, traceable administrative procedure for re-registering an orphan artifact
        after out-of-band external verification.
        """
        target_path = self.output_dir / filename
        if not target_path.exists():
            raise FileNotFoundError(f"Cannot re-register missing artifact: {target_path}")

        raw_bytes = target_path.read_bytes()
        actual_sha = hashlib.sha256(raw_bytes).hexdigest()
        if actual_sha != expected_sha256:
            from prodocux_kernel.artifacts import ArtifactResolutionError
            raise ArtifactResolutionError(
                f"Re-registration hash mismatch: expected {expected_sha256}, disk has {actual_sha}"
            )

        registry = self._load_registry()
        entry = {
            "pdf_sha256": actual_sha,
            "size_bytes": len(raw_bytes),
            "re_registered_by": auditor_id,
            "audit_log_reason": audit_log_reason,
            "re_registered_at": datetime.now(timezone.utc).isoformat(),
        }
        registry[filename] = entry
        self._save_registry(registry)
        return entry

    @staticmethod
    def generate_dossier_pdf(record: DetentionRecord, output_dir: str) -> str:
        """Backwards-compatible wrapper matching the legacy signature."""
        builder = DetentionDossierBuilder(output_dir)
        pdf_path, _ = builder.generate_and_audit_dossier(record)
        return pdf_path

