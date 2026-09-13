# Public Kernel and Engine boundary

## Published dependencies

The consumer pins and imports:

- `prodocux==0.3.0rc4`
- `pdx-artifact-engine==0.3.0a5`

Acceptance must run in a clean environment installed from public distributions. A local
checkout on `PYTHONPATH`, editable install, monkeypatched production call, or copied
upstream source invalidates the result.

## ProDocuX Kernel calls used

The detention adapter calls public Kernel modules to render the PDF, extract PDF text,
resolve the registered opaque artifact, and evaluate supported evidence checks. The
application supplies tariff arithmetic because this Kernel release has no formula check.
SHA-256 proves byte identity; it is not a digital signature or proof of payment.

## PDX Artifact Engine calls used

The dispatch adapter builds a domain plan and calls the public Engine's
`ApprovalLedger.record` and `ArtifactRuntime.execute_plan`. A completed intervention
is recognized only from the direct Engine result and validated outputs.

The application domain remains responsible for candidate selection, road distance,
pickup windows, equipment/weight fit, HOS, and reservation policy. The published Engine
does not solve VRP, combine loads or vehicles, create market freight, quote rates, or
guarantee an economically optimal schedule.

## Fail-closed conditions

The application records no benefit when there is no eligible source return order or
rate; a compliance or reservation check fails; Engine execution is uncertain; a run is
replayed from loose files; Kernel extraction/evidence checks fail; or artifact and claim
identity do not match.

## Upstream gaps

- `REQ-PDX-KERNEL-001`: public Kernel digital-signature API.
- `REQ-PDX-KERNEL-002`: Kernel arithmetic/formula evidence check.
- `REQ-PDX-KERNEL-004`: Kernel-native PDF text bounding boxes.
- `REQ-PDX-ENGINE-005`: authenticated recovery/reconciliation after restart.

These are disclosed constraints. Product code must not replace them with look-alike
local implementations.
