# Security and responsible publication

## Included

The public package contains application source, tests, dependency locks, interface
documentation, acceptance logic, and disclosed upstream gaps.

## Excluded

- organizer-provided workbooks, briefs, and presentations;
- derived scenario indexes and operational identifiers;
- generated dossiers, manifests, receipts, locks, and reconciliation state;
- virtual environments, build output, caches, editor metadata, and local paths;
- credentials, tokens, cookies, API keys, and environment files.

## Reporting

Report suspected vulnerabilities privately to the repository owner before public
disclosure. Include the affected revision, reproduction steps, impact, and a minimal
proof of concept without organizer data.

## Runtime controls

This is a hackathon prototype without production user authentication. Public deployment
must set `ROADSTAR_PUBLIC_DEMO=true`, which hides raw order, fleet, legacy dispatch,
and legacy artifact-list endpoints. Before broader deployment, add authentication, role
authorization, explicit CORS origins, TLS, request limits, audit retention, secret
management, and a data-retention policy.

Treat Engine receipts and SHA-256 digests as integrity evidence within their documented
scope, not as identity, authorization, digital signatures, or proof of carrier action.
