import React, { useState, useEffect } from 'react';
import { SimControlsBar, DateOption } from './components/SimControlsBar';
import { HistoricalMap } from './components/HistoricalMap';
import { PdxMap, InterventionItem } from './components/PdxMap';
import { HistoricalLedgerAndFeed } from './components/HistoricalLedgerAndFeed';
import { PdxLedgerAndFeed } from './components/PdxLedgerAndFeed';
import { BenchmarkModal } from './components/BenchmarkModal';
import { DossierReceiptModal } from './components/DossierReceiptModal';

export default function App() {
  const [geofences, setGeofences] = useState<any[]>([]);
  const [availableDates, setAvailableDates] = useState<DateOption[]>([]);
  const [targetDate, setTargetDate] = useState<string>('2026-08-14');
  const [isBenchmarkOpen, setIsBenchmarkOpen] = useState(false);
  const [selectedIntervention, setSelectedIntervention] = useState<InterventionItem | null>(null);

  // Manual Start by Default: simulation starts paused!
  const [isRunning, setIsRunning] = useState(false);
  const [simSpeed, setSimSpeed] = useState(15); // 15 mins per tick

  // Simulation State
  const [simState, setSimState] = useState<any>({
    target_date: '2026-08-14',
    sim_clock: '06:00:00 EST',
    sim_minute: 0,
    progress_pct: 0,
    is_finished: false,
    enable_stochastic: true,
    fleet_size: 0,
    baseline: {
      total_miles: 0,
      empty_miles: 0,
      deadhead_pct: 0,
      freight_revenue: 0,
      running_cost: 0,
      unbilled_detention_hours: 0,
      disputed_detention_loss: 0,
      net_profit: 0,
      running_count: 0,
      active_trucks: []
    },
    pdx: {
      total_miles: 0,
      empty_miles: 0,
      deadhead_pct: 0,
      freight_revenue: 0,
      new_backhaul_revenue: 0,
      running_cost: 0,
      billed_detention_hours: 0,
      recovered_detention_revenue: 0,
      net_profit: 0,
      running_count: 0,
      active_trucks: []
    },
    deltas: {
      empty_miles_saved: 0,
      fuel_saved_cad: 0,
      detention_gain_cad: 0,
      added_operating_cost_cad: 0,
      new_backhaul_revenue_cad: 0,
      net_profit_delta_cad: 0,
      interventions_count: 0
    },
    interventions: []
    ,backhaul_data_status: {
      eligible_source_orders: 0,
      revenue_eligible: false,
      reason: 'Source-priced order data has not been verified'
    }
  });

  // Initial Load: Geofences, Dates, Initial State
  useEffect(() => {
    fetch('/api/geofences')
      .then(res => res.json())
      .then(data => setGeofences(data))
      .catch(err => console.error(err));

    fetch('/api/simulator/dates')
      .then(res => res.json())
      .then(data => {
        setAvailableDates(data);
        if (data.length > 0 && !data.find((d: any) => d.date === targetDate)) {
          setTargetDate(data[0].date);
        }
      })
      .catch(err => console.error(err));

    fetch('/api/simulator/dual/state')
      .then(res => res.json())
      .then(data => setSimState(data))
      .catch(err => console.error(err));
  }, []);

  // Ticking Simulation Loop
  useEffect(() => {
    if (!isRunning || simState.is_finished) return;

    const interval = setInterval(() => {
      fetch('/api/simulator/dual/tick', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ elapsed_minutes: simSpeed })
      })
        .then(res => res.json())
        .then(data => setSimState(data))
        .catch(err => console.error(err));
    }, 1500);

    return () => clearInterval(interval);
  }, [isRunning, simSpeed, simState.is_finished]);

  const handleSelectDate = (newDate: string) => {
    setTargetDate(newDate);
    setIsRunning(false); // Reset to paused when user switches date!
    fetch('/api/simulator/dual/config', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ target_date: newDate })
    })
      .then(res => res.json())
      .then(data => setSimState(data))
      .catch(err => console.error(err));
  };

  const handleTogglePlay = () => {
    setIsRunning(!isRunning);
  };

  const handleToggleStochastic = () => {
    const nextVal = !simState.enable_stochastic;
    fetch('/api/simulator/dual/config', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ enable_stochastic: nextVal })
    })
      .then(res => res.json())
      .then(data => setSimState(data))
      .catch(err => console.error(err));
  };

  const handleReset = () => {
    setIsRunning(false); // Reset to paused!
    fetch('/api/simulator/dual/reset', { method: 'POST' })
      .then(res => res.json())
      .then(data => setSimState(data))
      .catch(err => console.error(err));
  };

  return (
    <div className="min-h-screen w-full bg-slate-950 text-slate-100 font-sans select-none overflow-y-auto">
      {/* Top Header & Simulation Controls (Sticky) */}
      <SimControlsBar
        clockStr={simState.sim_clock}
        progressPct={simState.progress_pct}
        isRunning={isRunning}
        speed={simSpeed}
        enableStochastic={simState.enable_stochastic}
        targetDate={targetDate}
        availableDates={availableDates}
        fleetSize={simState.fleet_size || simState.baseline.active_trucks.length}
        onSelectDate={handleSelectDate}
        onTogglePlay={handleTogglePlay}
        onChangeSpeed={setSimSpeed}
        onToggleStochastic={handleToggleStochastic}
        onReset={handleReset}
        onOpenBenchmark={() => setIsBenchmarkOpen(true)}
      />

      {/* Main Dual Theater: 100% Width 50/50 Balanced Split */}
      <div className="w-full flex flex-row">
        {/* ================= LEFT HALF: 🔴 HISTORICAL REALITY BASELINE (50% WIDTH) ================= */}
        <div className="w-1/2 flex flex-col border-r border-slate-800">
          {/* Section Header */}
          <div className="bg-slate-900 px-4 py-2 border-b border-slate-800 flex items-center justify-between shrink-0">
            <div className="flex items-center space-x-2">
              <span className="w-3 h-3 rounded-full bg-rose-600 animate-pulse"></span>
              <div>
                <h2 className="text-xs font-black tracking-wider text-rose-400 uppercase">
                  Historical Reality Track (Manual Dispatch Baseline)
                </h2>
                <p className="text-[10px] text-slate-400">
                  {simState.baseline.active_trucks.length} Released Legs · {simState.baseline.deadhead_pct.toFixed(1)}% Empty Miles · No PDX Intervention
                </p>
              </div>
            </div>
            <span className="bg-rose-950 text-rose-300 border border-rose-800 text-[10px] font-mono px-2 py-0.5 rounded font-bold">
              HISTORICAL BASELINE
            </span>
          </div>

          {/* Large Prominent Map (560px height) */}
          <div className="h-[560px] w-full relative">
            <HistoricalMap
              trucks={simState.baseline.active_trucks}
              geofences={geofences}
            />
          </div>

          {/* Full-Fleet Ledger & Roster Table (Generous Height) */}
          <HistoricalLedgerAndFeed baseline={simState.baseline} />
        </div>

        {/* ================= RIGHT HALF: 🟢 PDX AUTONOMOUS INTERVENTION (50% WIDTH) ================= */}
        <div className="w-1/2 flex flex-col">
          {/* Section Header */}
          <div className="bg-slate-900 px-4 py-2 border-b border-slate-800 flex items-center justify-between shrink-0">
            <div className="flex items-center space-x-2">
              <span className="w-3 h-3 rounded-full bg-emerald-400 animate-ping"></span>
              <div>
                <h2 className="text-xs font-black tracking-wider text-emerald-300 uppercase">
                  PDX Autonomous Operations (Artifact Engine &amp; ProDocuX)
                </h2>
                <p className="text-[10px] text-slate-400">
                  {simState.pdx.active_trucks.length} Released Legs · {simState.deltas.interventions_count} Completed Interventions · Only Engine/Kernel Outcomes Credited
                </p>
              </div>
            </div>
            <span className="bg-emerald-950 text-emerald-300 border border-emerald-700 text-[10px] font-mono px-2 py-0.5 rounded font-bold">
              PDX AUTONOMOUS KERNEL
            </span>
          </div>

          {!simState.backhaul_data_status?.revenue_eligible && (
            <div className="bg-amber-950/70 border-b border-amber-800 px-4 py-2 text-[11px] text-amber-200 font-mono">
              Backhaul accounting blocked: {simState.backhaul_data_status?.reason}
            </div>
          )}

          {/* Large Prominent Map with Floating Callouts (560px height) */}
          <div className="h-[560px] w-full relative">
            <PdxMap
              trucks={simState.pdx.active_trucks}
              geofences={geofences}
              interventions={simState.interventions}
              simMinute={simState.sim_minute}
              onSelectIntervention={(inv) => setSelectedIntervention(inv)}
            />
          </div>

          {/* PDX Advantage Ledger & Accumulating Feed with Physical Receipts */}
          <PdxLedgerAndFeed
            pdx={simState.pdx}
            deltas={simState.deltas}
            interventions={simState.interventions}
            baselineTrucks={simState.baseline.active_trucks}
            onSelectIntervention={(inv) => setSelectedIntervention(inv)}
          />
        </div>
      </div>

      {/* Cryptographic Dossier / Artifact Receipt Modal */}
      <DossierReceiptModal
        intervention={selectedIntervention}
        onClose={() => setSelectedIntervention(null)}
      />

      {/* Real-Data 105-Order Benchmark Modal */}
      <BenchmarkModal
        isOpen={isBenchmarkOpen}
        onClose={() => setIsBenchmarkOpen(false)}
      />

      <a
        href="https://github.com/pdx-experimental/pdx-roadstar"
        target="_blank"
        rel="noreferrer"
        className="fixed bottom-2 right-3 z-[2000] rounded border border-slate-700 bg-slate-950/90 px-2 py-1 text-[10px] text-slate-300 hover:text-white"
      >
        Source · AGPL-3.0-or-later
      </a>
    </div>
  );
}
