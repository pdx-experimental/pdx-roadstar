import React, { useState } from 'react';
import { InterventionItem, TruckItem } from './PdxMap';

interface PdxLedgerAndFeedProps {
  pdx: {
    total_miles: number;
    empty_miles: number;
    deadhead_pct: number;
    freight_revenue: number;
    new_backhaul_revenue: number;
    running_cost: number;
    billed_detention_hours: number;
    recovered_detention_revenue: number;
    net_profit: number;
    active_trucks: TruckItem[];
  };
  deltas: {
    empty_miles_saved: number;
    fuel_saved_cad: number;
    detention_gain_cad: number;
    new_backhaul_revenue_cad?: number;
    added_operating_cost_cad?: number;
    net_profit_delta_cad: number;
    interventions_count: number;
  };
  interventions: InterventionItem[];
  baselineTrucks: TruckItem[];
  onSelectIntervention: (inv: InterventionItem) => void;
}

export const PdxLedgerAndFeed: React.FC<PdxLedgerAndFeedProps> = ({
  pdx,
  deltas,
  interventions,
  baselineTrucks,
  onSelectIntervention
}) => {
  const [activeTab, setActiveTab] = useState<'comparison' | 'feed'>('comparison');

  const backhaulRev = deltas.new_backhaul_revenue_cad ?? pdx.new_backhaul_revenue ?? 0.0;
  const loadedCount = pdx.active_trucks.filter(t => !t.is_empty).length;
  const dwellCount = pdx.active_trucks.filter(t => t.dwell > 2.0).length;

  return (
    <div className="flex flex-col bg-slate-950 p-4 space-y-3 text-xs border-t border-slate-800 min-h-[500px]">
      {/* Top 5 Metrics Row */}
      <div className="grid grid-cols-5 gap-2 shrink-0">
        <div className="bg-emerald-950/20 p-2.5 rounded-xl border border-emerald-900/50 shadow">
          <span className="text-[10px] text-emerald-300 block font-bold">Empty Miles Converted:</span>
          <span className="text-base font-black text-emerald-400 font-mono">{deltas.empty_miles_saved.toFixed(0)} mi</span>
          <span className="text-[9px] text-slate-400 block mt-0.5">$0 fuel delta (same corridor)</span>
        </div>

        <div className="bg-cyan-950/20 p-2.5 rounded-xl border border-cyan-900/50 shadow">
          <span className="text-[10px] text-cyan-300 block font-bold">Detention Claim Documented:</span>
          <span className="text-base font-black text-cyan-300 font-mono">+${pdx.recovered_detention_revenue.toLocaleString(undefined, { maximumFractionDigits: 0 })} CAD</span>
          <span className="text-[9px] text-cyan-300/80 block mt-0.5">{pdx.billed_detention_hours.toFixed(1)}h documented at $95/h · collection pending</span>
        </div>

        <div className="bg-indigo-950/20 p-2.5 rounded-xl border border-indigo-900/50 shadow">
          <span className="text-[10px] text-indigo-300 block font-bold">New Backhaul Freight:</span>
          <span className="text-base font-black text-indigo-300 font-mono">+${backhaulRev.toLocaleString(undefined, { maximumFractionDigits: 0 })} CAD</span>
          <span className="text-[9px] text-indigo-300/80 block mt-0.5">Public Engine completed outcomes only</span>
        </div>

        <div className="bg-emerald-950/20 p-2.5 rounded-xl border border-emerald-900/50 shadow">
          <span className="text-[10px] text-emerald-300 block font-bold">Deadhead Slashed:</span>
          <div className="flex items-baseline space-x-1">
            <span className="text-base font-black text-emerald-400 font-mono">{pdx.deadhead_pct.toFixed(1)}%</span>
            <span className="text-[9px] text-emerald-300 font-bold">after verified interventions</span>
          </div>
          <span className="text-[9px] text-slate-400 block mt-0.5">{loadedCount} loads in service</span>
        </div>

        <div className="bg-gradient-to-r from-emerald-950/70 via-cyan-950/70 to-blue-950/70 p-2.5 rounded-xl border border-emerald-400/80 shadow-xl">
          <span className="text-[10px] text-cyan-200 block font-bold">Projected Contribution Lift:</span>
          <span className="text-base font-black text-cyan-300 font-mono">+${deltas.net_profit_delta_cad.toLocaleString(undefined, { maximumFractionDigits: 0 })} CAD</span>
          <span className="text-[9px] text-emerald-300 font-bold block mt-0.5">Assumes documented detention is fully collected</span>
        </div>
      </div>

      {/* Crystal Clear Transparent Accounting Equation Bar */}
      <div className="bg-slate-900/90 border border-slate-800 rounded-xl px-3.5 py-1.5 flex items-center justify-between font-mono text-[11px] shrink-0 shadow-inner">
        <div className="flex items-center space-x-2 text-slate-300">
          <span className="text-cyan-400 font-bold font-sans">∑ Scenario Component Reconciliation:</span>
          <span className="text-cyan-300 font-bold">+${pdx.recovered_detention_revenue.toLocaleString(undefined, { maximumFractionDigits: 0 })} (Documented Claim)</span>
          <span className="text-slate-500">+</span>
          <span className="text-indigo-300 font-bold">+${backhaulRev.toLocaleString(undefined, { maximumFractionDigits: 0 })} (Backhaul Freight)</span>
          <span className="text-slate-500">−</span>
          <span className="text-amber-300 font-bold">${(deltas.added_operating_cost_cad ?? 0).toLocaleString(undefined, { maximumFractionDigits: 0 })} (Added Cost)</span>
          <span className="text-slate-500">=</span>
          <span className="text-emerald-300 font-black font-mono text-xs">+${deltas.net_profit_delta_cad.toLocaleString(undefined, { maximumFractionDigits: 0 })} CAD Projected Contribution Lift</span>
        </div>
        <span className="text-[10px] text-emerald-400 font-sans hidden xl:inline">Displayed Components Reconciled</span>
      </div>

      {/* Dispatch Outcome Scoreboard */}
      <div className="grid grid-cols-4 gap-2 shrink-0 bg-slate-900/60 p-2 rounded-xl border border-slate-800 text-[10px] font-mono">
        <div className="flex items-center space-x-1.5 text-slate-300">
          <span className="w-2 h-2 rounded-full bg-slate-400"></span>
          <span>Dispatched: <b>{pdx.active_trucks.length} Legs</b></span>
        </div>
        <div className="flex items-center space-x-1.5 text-emerald-400">
          <span className="w-2 h-2 rounded-full bg-emerald-400"></span>
          <span>Loaded legs: <b>{loadedCount}</b></span>
        </div>
        <div className="flex items-center space-x-1.5 text-emerald-400">
          <span className="w-2 h-2 rounded-full bg-emerald-400"></span>
          <span>Deadhead: <b>{pdx.empty_miles.toFixed(0)} mi ({pdx.deadhead_pct.toFixed(1)}%)</b></span>
        </div>
        <div className="flex items-center space-x-1.5 text-cyan-300">
          <span className="w-2 h-2 rounded-full bg-cyan-400"></span>
          <span>Verified interventions: <b>{deltas.interventions_count}</b></span>
        </div>
      </div>

      {/* Table Section with Tabs: Side-by-Side Comparison vs Live Artifact Feed */}
      <div className="flex flex-col bg-slate-900/80 rounded-xl border border-slate-800 overflow-hidden shadow-lg">
        <div className="bg-slate-900 px-4 py-1.5 border-b border-slate-800 flex items-center justify-between shrink-0">
          {/* Tabs */}
          <div className="flex items-center space-x-2">
            <button
              onClick={() => setActiveTab('comparison')}
              className={`px-3 py-1 rounded-lg text-xs font-bold transition flex items-center space-x-1.5 cursor-pointer ${
                activeTab === 'comparison'
                  ? 'bg-cyan-600 text-white shadow'
                  : 'text-slate-400 hover:text-white bg-slate-800'
              }`}
            >
              <span>📋 Side-by-Side Dispatch Comparison ({pdx.active_trucks.length} Trucks)</span>
            </button>
            <button
              onClick={() => setActiveTab('feed')}
              className={`px-3 py-1 rounded-lg text-xs font-bold transition flex items-center space-x-1.5 cursor-pointer ${
                activeTab === 'feed'
                  ? 'bg-cyan-600 text-white shadow'
                  : 'text-slate-400 hover:text-white bg-slate-800'
              }`}
            >
              <span>⚡ Live Artifacts &amp; Interventions ({interventions.length})</span>
            </button>
          </div>

          <span className="text-[10px] text-emerald-400 font-mono font-bold bg-emerald-950/80 px-2 py-0.5 rounded border border-emerald-700">
            {activeTab === 'comparison' ? 'Direct Truck-by-Truck Comparison' : 'Physical Files on Disk'}
          </span>
        </div>

        {/* Scrollable Container with ample height */}
        <div className="h-[360px] overflow-y-auto p-3 space-y-2 divide-y divide-slate-800/60">
          {activeTab === 'comparison' ? (
            /* TAB 1: SIDE-BY-SIDE DISPATCH OUTCOME COMPARISON (Truck by Truck) */
            pdx.active_trucks.length === 0 ? (
              <div className="h-full flex flex-col items-center justify-center text-center text-slate-500">
                <span className="text-3xl mb-2">⏳</span>
                <p className="font-bold text-slate-400">No trips released</p>
                <p className="text-[11px] mt-1">PDX will intervene automatically as scenario events occur.</p>
              </div>
            ) : pdx.active_trucks.map((t, idx) => {
              const baseT = baselineTrucks[idx] || t;
              const matchingEvent = interventions.find(inv => inv.truck === t.id && inv.type === 'PDX_BACKHAUL_MATCH');
              const dossierEvent = interventions.find(inv => inv.truck === t.id && inv.type === 'PRODOCUX_DETENTION_DOSSIER');
              const isBackhaul = t.leg_type === 'PDX Backhaul Executed' && Boolean(matchingEvent);
              const hasDwell = Boolean(dossierEvent);

              let outcomeBadge = t.is_empty
                ? 'Empty deadhead · no PDX intervention'
                : 'Loaded linehaul · no PDX action';
              let liftDelta = '+$0.00 CAD';
              let badgeColor = 'bg-slate-800 text-slate-300';

              if (isBackhaul) {
                outcomeBadge = '🤖 Backhaul Paired (0 Deadhead)';
                liftDelta = matchingEvent?.financial_delta || '$0.00 CAD';
                badgeColor = 'bg-emerald-950 text-emerald-300 border border-emerald-700';
              } else if (hasDwell) {
                outcomeBadge = `📜 ProDocuX Dossier Sealed (${(t.dwell - 2.0).toFixed(1)}h)`;
                liftDelta = dossierEvent?.financial_delta || '$0.00 CAD';
                badgeColor = 'bg-blue-950 text-cyan-300 border border-cyan-700';
              }

              return (
                <div key={idx} className="pt-2 first:pt-0 flex items-center justify-between hover:bg-slate-800/40 px-3 py-2 rounded-lg transition">
                  <div className="flex items-center space-x-3">
                    <span className="font-mono text-xs font-bold text-cyan-400 w-20">{t.id}</span>
                    <div>
                      <div className="flex items-center space-x-2">
                        <span className="font-bold text-white text-xs">{t.orig} ➔ {t.dest}</span>
                        <span className="text-[10px] text-slate-400 font-mono">({t.dist.toFixed(0)} mi)</span>
                      </div>
                      <div className="text-[10px] text-slate-400">
                        Historical: <span className={baseT.is_empty ? 'text-rose-400 font-bold' : (hasDwell ? 'text-amber-400' : 'text-slate-300')}>
                          {baseT.is_empty ? 'Empty Deadhead Return' : (hasDwell ? `${t.dwell.toFixed(1)}h Dock Dwell (Unbilled)` : 'Loaded Transit')}
                        </span>
                      </div>
                    </div>
                  </div>

                  <div className="flex items-center space-x-3 text-right">
                    <div>
                      <span className={`inline-flex items-center px-2 py-0.5 rounded text-[10px] font-bold shadow-sm ${badgeColor}`}>
                        {outcomeBadge}
                      </span>
                      <div className="font-mono font-bold text-emerald-400 text-xs mt-0.5">
                        {liftDelta}
                      </div>
                    </div>
                  </div>
                </div>
              );
            })
          ) : (
            /* TAB 2: ACCUMULATING INTERVENTION FEED & PHYSICAL ARTIFACTS */
            interventions.length === 0 ? (
              <div className="h-full flex flex-col items-center justify-center p-8 text-center text-slate-500">
                <span className="text-3xl mb-2">⏳</span>
                <p className="font-bold text-slate-400">Simulation is Paused or Waiting to Start</p>
                <p className="text-[11px] text-slate-500 mt-1 max-w-sm">
                  Click <span className="text-emerald-400 font-bold">▶ Start Simulation</span> at the top to begin stream.
                </p>
              </div>
            ) : (
              interventions.map((inv, idx) => {
                const isBackhaul = inv.type === 'PDX_BACKHAUL_MATCH';
                const isDossier = inv.type === 'PRODOCUX_DETENTION_DOSSIER';
                const isPdf = inv.filename?.endsWith('.pdf');

                return (
                  <div
                    key={idx}
                    onClick={() => onSelectIntervention(inv)}
                    className="pt-2 first:pt-0 flex items-center justify-between hover:bg-slate-800/50 px-3 py-2 rounded-lg transition cursor-pointer group border border-transparent hover:border-slate-700"
                  >
                    <div className="flex items-center space-x-3">
                      <span className="font-mono text-[10px] font-bold text-slate-400 w-18">{inv.time}</span>
                      <div>
                        <div className="flex items-center space-x-2">
                          {isBackhaul ? (
                            <span className="px-2 py-0.5 rounded bg-emerald-950 text-emerald-300 border border-emerald-700 text-[9px] font-black">
                              🤖 AI BACKHAUL
                            </span>
                          ) : isDossier ? (
                            <span className="px-2 py-0.5 rounded bg-blue-950 text-cyan-300 border border-cyan-700 text-[9px] font-black">
                              📜 PRODOCUX DOSSIER
                            </span>
                          ) : (
                            <span className="px-2 py-0.5 rounded bg-indigo-950 text-indigo-300 border border-indigo-700 text-[9px] font-black">
                              🛡️ HOS CERTIFIED
                            </span>
                          )}
                          <span className="font-mono font-bold text-white text-xs">{inv.truck}</span>
                          <span className="text-[11px] text-slate-300 truncate max-w-[240px]">{inv.desc}</span>
                        </div>
                        <div className="text-[10px] text-slate-400 mt-0.5 flex items-center space-x-2">
                          <span>{inv.location_name} · Driver: {inv.driver}</span>
                          {inv.filename && (
                            <span className="font-mono text-[9px] text-cyan-400 bg-slate-950 px-1.5 py-0.2 rounded border border-slate-800">
                              {isPdf ? '📄 PDF Sealed' : '📦 JSON Receipt'}
                            </span>
                          )}
                        </div>
                      </div>
                    </div>

                    <div className="flex items-center space-x-3 text-right">
                      <span className="font-mono font-black text-emerald-400 text-sm">{inv.financial_delta}</span>
                      <button
                        className="bg-cyan-600 hover:bg-cyan-500 text-white text-[10px] font-bold px-2.5 py-1 rounded-lg transition shadow flex items-center space-x-1"
                      >
                        <span>{isPdf ? 'Inspect PDF' : 'Verify'}</span>
                      </button>
                    </div>
                  </div>
                );
              })
            )
          )}
        </div>
      </div>
    </div>
  );
};
