# PDX RoadStar

PDX RoadStar is a Southern Ontario dispatch simulation and intervention audit demo for
the RoadStar Hackathon 2026. It compares the same historical fleet scenario under two
conditions:

- baseline: the simulator replays the source scenario without PDX intervention;
- managed: due events may trigger a documented detention claim or an eligible backhaul
  workflow through the published ProDocuX Kernel and PDX Artifact Engine.

The simulator and PDX manager are separate components. Before simulation time advances,
both views contain zero active trips and zero interventions. The manager receives events
from the scenario as they become due; it does not pre-create trips or invent freight.

## Live Demo & Deployment

- **Live Demo**: `https://pdx-roadstar.onrender.com` (Hosted on Render)
- **Architecture**: A dual-repository structure is maintained for hackathon compliance and data governance. Public code is audited in this repository; the live deployment is fed with authorized operational data via the deployment repository (`pdx-roadstar-deploy`). See [DEPLOYMENT.md](docs/DEPLOYMENT.md).

## What the demo proves

- A dedicated simulator advances GPS, speed, distance, dock dwell, and HOS-related state.
- The comparison layer applies PDX interventions only after a simulated event is due.
- Detention dossiers use public `prodocux==0.3.0rc4` rendering, PDF intake, artifact
  resolution, and evidence-verification APIs.
- Dispatch plans use public `pdx-artifact-engine==0.3.0a5` `ApprovalLedger` and
  `ArtifactRuntime.execute_plan` APIs.
- Backhaul credit requires an external source order with a usable rate, time window,
  equipment/weight fit, driver HOS fit, and successful Engine execution.
- Missing rates, missing source freight, failed verification, and uncertain Engine
  outcomes produce zero financial credit.

The current event workbook does not expose a source freight-rate field usable by this
adapter. Therefore the audited demo reports **zero new backhaul revenue**. Detention
recovery is a modeled claim amount at the configured tariff; it is not cash collected
or a guaranteed business outcome.

## Capability boundary

The domain layer performs freight matching, distance calculations, HOS checks, weight
checks, and plan construction. The PDX Artifact Engine validates and executes resulting
plan steps and produces receipts/manifests. It is not a vehicle-routing,
load-consolidation, or fleet-optimization solver.

The public Engine cannot authenticate completed or interrupted dispatch state from loose
files after restart. Such cases stop at `awaiting_reconciliation`; see
[ENGINE_BOUNDARY.md](docs/ENGINE_BOUNDARY.md).

## Repository layout

```text
apps/api/                           FastAPI service and REST endpoints
apps/web/                           React/Vite dashboard
packages/roadstar_domain/           Freight, HOS, geofence and resource logic
packages/roadstar_application/      Scenario/manager comparison
packages/roadstar_adapter_pdx/      Public PDX Artifact Engine adapter
packages/roadstar_adapter_prodocux/ Public ProDocuX Kernel adapter
simulator/                          Independent fleet simulator
tests/                              Contract, regression and accounting tests
scripts/                            Reproducibility and acceptance checks
docs/                               Submission, security and review material
```

## Data

Organizer-provided files and derived operational records are absent from this public
tree. Authorized evaluators can configure them using `ROADSTAR_DATASET_PATH` and
`ROADSTAR_SCENARIO_INDEX_PATH`. See [DATA_GOVERNANCE.md](docs/DATA_GOVERNANCE.md).

## Local setup

Requirements: Python 3.11+, Node.js 20+, and pnpm.

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install --require-hashes -r requirements.lock
pnpm --dir apps/web install --frozen-lockfile
pnpm --dir apps/web build
```

Configure the two authorized data paths, then run:

```powershell
$env:ROADSTAR_DATASET_PATH = "D:\authorized\Hackathon_Data.xlsx"
$env:ROADSTAR_SCENARIO_INDEX_PATH = "D:\authorized\indexed_scenarios.json"
.\.venv\Scripts\python.exe -m pytest tests -q
.\.venv\Scripts\python.exe apps/api/main.py
```

Open `http://localhost:8000/`.

## License

PDX RoadStar is licensed under AGPL-3.0-or-later. The hosted demo must provide users a
link to the corresponding public source revision. Third-party components keep their own
licenses; see [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md).

## Documentation

- [Deployment architecture](docs/DEPLOYMENT.md)
- [Data governance](docs/DATA_GOVERNANCE.md)
- [Engine capability boundary](docs/ENGINE_BOUNDARY.md)
- [Security & compliance policy](docs/SECURITY.md)
