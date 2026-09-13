# Data governance and model card

## Publication decision

This public tree excludes organizer-provided XLSX, PDF, and PPTX files and excludes the
generated `indexed_scenarios.json`. The index contains derived trip, truck, driver,
route, distance, dwell, and date records. A public event page does not itself grant
redistribution rights for those records.

Generated PDFs, receipts, manifests, reconciliation state, test evidence, local locks,
and runtime logs are also excluded.

## Runtime provenance

Every scenario leg must originate from the configured scenario index. Every candidate
backhaul must originate from the configured order source. The manager may change an
existing due event's handling; it may not add freight, invent a rate, or count a
pre-simulation trip.

The UI must show zero active trips and interventions at minute zero. Counts shown later
are leg counts, not necessarily unique trucks. Baseline and managed views replay the
same released legs; an intervention changes an outcome and does not silently create an
extra source trip.

## Financial semantics

- Freight revenue and operating cost are modeled from source fields and declared
  parameters.
- Detention recovery is a documented claim at CAD 95/hour after a two-hour free period.
- New backhaul revenue is zero unless a source order has a usable rate and the complete
  dispatch path succeeds.
- Net margin lift equals backhaul revenue plus documented detention claims minus added
  operating cost.
- Fuel savings remain zero unless route calculation demonstrates distance reduction.

Results are scenario estimates, not audited statements, cash collections, or guarantees.
No annualization is presented without a supported operating-day model.

## Known limitation

The scenario index is a preprocessed authorized local input; its generator is outside
this public package. The current workbook lacks a usable freight-rate field for the
backhaul adapter, so the current audited result has no backhaul revenue.
