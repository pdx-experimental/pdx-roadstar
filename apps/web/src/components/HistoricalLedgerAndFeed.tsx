import React from 'react';
import { TruckItem } from './HistoricalMap';

interface HistoricalLedgerAndFeedProps {
  baseline: {
    total_miles: number;
    empty_miles: number;
    deadhead_pct: number;
    freight_revenue: number;
    running_cost: number;
    unbilled_detention_hours: number;
    disputed_detention_loss: number;
    net_profit: number;
    active_trucks: TruckItem[];
  };
}

export const HistoricalLedgerAndFeed: React.FC<HistoricalLedgerAndFeedProps> = ({ baseline }) => {
  const loadedCount = baseline.active_trucks.filter(t => !t.is_empty).length;
  const emptyCount = baseline.active_trucks.filter(t => t.is_empty).length;
  const dwellCount = baseline.active_trucks.filter(t => t.dwell > 2.0).length;

  return (
    <div className="flex flex-col bg-slate-950 p-4 space-y-3 text-xs border-t border-slate-800 min-h-[500px]">
      {/* Top 5 Metrics Row */}
      <div className="grid grid-cols-5 gap-2 shrink-0">
        <div className="bg-slate-900 p-2.5 rounded-xl border border-slate-800 shadow">
          <span className="text-[10px] text-slate-400 block font-bold">Total Fleet Miles:</span>
          <span className="text-base font-black text-white font-mono">{baseline.total_miles.toLocaleString()} mi</span>
          <span className="text-[9px] text-slate-500 block mt-0.5">Loaded: {(baseline.total_miles - baseline.empty_miles).toFixed(0)} mi</span>
        </div>

        <div className="bg-rose-950/20 p-2.5 rounded-xl border border-rose-900/50 shadow">
          <span className="text-[10px] text-rose-300 block font-bold">Deadhead Ratio:</span>
          <span className="text-base font-black text-rose-400 font-mono">{baseline.deadhead_pct.toFixed(1)}%</span>
          <span className="text-[9px] text-rose-400/80 block mt-0.5">{baseline.empty_miles.toFixed(0)} mi empty ({emptyCount} legs)</span>
        </div>

        <div className="bg-slate-900 p-2.5 rounded-xl border border-slate-800 shadow">
          <span className="text-[10px] text-slate-400 block font-bold">Operating Cost:</span>
          <span className="text-base font-black text-slate-200 font-mono">${baseline.running_cost.toLocaleString(undefined, { maximumFractionDigits: 0 })} CAD</span>
          <span className="text-[9px] text-slate-500 block mt-0.5">$1.85 / mi fuel &amp; maintenance</span>
        </div>

        <div className="bg-amber-950/20 p-2.5 rounded-xl border border-amber-900/50 shadow">
          <span className="text-[10px] text-amber-300 block font-bold">Unbilled Dwell Loss:</span>
          <span className="text-base font-black text-amber-400 font-mono">-${baseline.disputed_detention_loss.toLocaleString(undefined, { maximumFractionDigits: 0 })} CAD</span>
          <span className="text-[9px] text-amber-300/80 block mt-0.5">{baseline.unbilled_detention_hours.toFixed(1)}h unbilled ({dwellCount} docks)</span>
        </div>

        <div className="bg-slate-900 p-2.5 rounded-xl border border-slate-800 shadow">
          <span className="text-[10px] text-slate-400 block font-bold">Historical Contribution Margin:</span>
          <span className={`text-base font-black font-mono ${baseline.net_profit >= 0 ? 'text-white' : 'text-rose-400'}`}>
            ${baseline.net_profit.toLocaleString(undefined, { maximumFractionDigits: 0 })} CAD
          </span>
          <span className="text-[9px] text-slate-500 block mt-0.5">Modeled loaded-mile value − modeled cost</span>
        </div>
      </div>

      {/* Accounting Breakdown Equation Bar */}
      <div className="bg-slate-900/90 border border-slate-800 rounded-xl px-3.5 py-1.5 flex items-center justify-between font-mono text-[11px] shrink-0 shadow-inner">
        <div className="flex items-center space-x-2 text-slate-300">
          <span className="text-rose-400 font-bold font-sans">Historical Accounting:</span>
          <span className="text-slate-200 font-bold">${baseline.freight_revenue.toLocaleString(undefined, { maximumFractionDigits: 0 })} (Modeled Loaded Value)</span>
          <span className="text-slate-500">-</span>
          <span className="text-rose-400 font-bold">${baseline.running_cost.toLocaleString(undefined, { maximumFractionDigits: 0 })} (Cost)</span>
          <span className="text-slate-500">=</span>
          <span className="text-white font-black font-mono text-xs">${baseline.net_profit.toLocaleString(undefined, { maximumFractionDigits: 0 })} CAD Contribution Margin</span>
          <span className="text-amber-400 font-sans text-[10px]">(-${baseline.disputed_detention_loss.toLocaleString(undefined, { maximumFractionDigits: 0 })} Dwell Unclaimed)</span>
        </div>
        <span className="text-[10px] text-slate-500 font-sans hidden xl:inline">Manual Dispatch Reality</span>
      </div>

      {/* Dispatch Outcome Scoreboard */}
      <div className="grid grid-cols-4 gap-2 shrink-0 bg-slate-900/60 p-2 rounded-xl border border-slate-800 text-[10px] font-mono">
        <div className="flex items-center space-x-1.5 text-slate-300">
          <span className="w-2 h-2 rounded-full bg-slate-400"></span>
          <span>Dispatched: <b>{baseline.active_trucks.length} Legs</b></span>
        </div>
        <div className="flex items-center space-x-1.5 text-slate-300">
          <span className="w-2 h-2 rounded-full bg-emerald-500"></span>
          <span>Loaded: <b>{loadedCount} ({((loadedCount / Math.max(1, baseline.active_trucks.length)) * 100).toFixed(1)}%)</b></span>
        </div>
        <div className="flex items-center space-x-1.5 text-rose-400">
          <span className="w-2 h-2 rounded-full bg-rose-500"></span>
          <span>Deadhead: <b>{emptyCount} ({baseline.deadhead_pct.toFixed(1)}%)</b></span>
        </div>
        <div className="flex items-center space-x-1.5 text-amber-400">
          <span className="w-2 h-2 rounded-full bg-amber-500"></span>
          <span>Unbilled Dwell: <b>{dwellCount} Delays</b></span>
        </div>
      </div>

      {/* Historical Fleet Dispatch Outcome Table */}
      <div className="flex flex-col bg-slate-900/80 rounded-xl border border-slate-800 overflow-hidden shadow-lg">
        <div className="bg-slate-900 px-4 py-2 border-b border-slate-800 flex items-center justify-between shrink-0">
          <div className="flex items-center space-x-2">
            <span className="text-sm">📋</span>
            <span className="text-xs font-bold text-slate-200 uppercase tracking-wider">
              Historical Dispatch Outcomes ({baseline.active_trucks.length} Trucks)
            </span>
          </div>
          <span className="text-[10px] text-rose-400 font-mono font-bold bg-rose-950/80 px-2 py-0.5 rounded border border-rose-800">
            Unoptimized Baseline Roster
          </span>
        </div>

        {/* Scrollable Container with ample height */}
        <div className="h-[360px] overflow-y-auto p-3 space-y-2 divide-y divide-slate-800/60">
          {baseline.active_trucks.length === 0 && (
            <div className="h-full flex flex-col items-center justify-center text-center text-slate-500">
              <span className="text-3xl mb-2">⏳</span>
              <p className="font-bold text-slate-400">No trips released</p>
              <p className="text-[11px] mt-1">Start the simulation to release scheduled trips.</p>
            </div>
          )}
          {baseline.active_trucks.map((t, idx) => (
            <div key={idx} className="pt-2 first:pt-0 flex items-center justify-between hover:bg-slate-800/40 px-3 py-2 rounded-lg transition">
              <div className="flex items-center space-x-3">
                <span className="font-mono text-xs font-bold text-slate-400 w-20">{t.id}</span>
                <div>
                  <div className="flex items-center space-x-2">
                    <span className="font-bold text-white text-xs">{t.orig} ➔ {t.dest}</span>
                    <span className="text-[10px] text-slate-400 font-mono">({t.dist.toFixed(0)} mi)</span>
                  </div>
                  <div className="text-[10px] text-slate-400">
                    Driver: {t.driver} · Speed: {t.speed.toFixed(0)} km/h · {t.status}
                  </div>
                </div>
              </div>

              <div className="text-right">
                {t.is_empty ? (
                  <span className="inline-flex items-center px-2 py-1 rounded bg-rose-950 text-rose-300 border border-rose-800 text-[10px] font-bold shadow-sm">
                    ⚠️ Empty Deadhead (-${(t.dist * 1.85).toFixed(0)} Cost)
                  </span>
                ) : t.dwell > 2.0 ? (
                  <span className="inline-flex items-center px-2 py-1 rounded bg-amber-950 text-amber-300 border border-amber-800 text-[10px] font-bold shadow-sm">
                    ⏳ {t.dwell.toFixed(1)}h Dwell (-${((t.dwell - 2.0) * 95).toFixed(0)} Loss)
                  </span>
                ) : (
                  <span className="inline-flex items-center px-2 py-1 rounded bg-slate-800 text-slate-300 text-[10px]">
                    ✓ Loaded Linehaul (${(t.dist * 2.85).toFixed(0)} modeled value)
                  </span>
                )}
              </div>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
};
