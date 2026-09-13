import React from 'react';

interface TrackMetrics {
  total_miles: number;
  empty_miles: number;
  deadhead_pct: number;
  freight_revenue: number;
  running_cost: number;
  unbilled_detention_hours?: number;
  disputed_detention_loss?: number;
  billed_detention_hours?: number;
  recovered_detention_revenue?: number;
  net_profit: number;
  hos_violations: number;
}

interface DualTrackLedgerProps {
  baseline: TrackMetrics;
  pdx: TrackMetrics;
  deltas: {
    empty_miles_saved: number;
    detention_gain_cad: number;
    net_profit_delta_cad: number;
    interventions_count: number;
  };
}

export const DualTrackLedger: React.FC<DualTrackLedgerProps> = ({ baseline, pdx, deltas }) => {
  return (
    <div className="bg-slate-900 border border-slate-800 rounded-xl p-4 shadow-xl flex flex-col space-y-4">
      {/* Top Gain Summary Bar */}
      <div className="bg-gradient-to-r from-emerald-950/70 via-cyan-950/80 to-blue-950/70 border border-cyan-800/80 rounded-xl p-3 flex items-center justify-between shadow-lg">
        <div className="flex items-center space-x-3">
          <div className="w-10 h-10 rounded-full bg-cyan-500/20 border border-cyan-400 flex items-center justify-center text-xl">
            🚀
          </div>
          <div>
            <span className="text-[11px] font-bold text-cyan-300 uppercase tracking-wider block">
              LIVE REAL-TIME GAIN FROM PDX INTERVENTIONS
            </span>
            <span className="text-[10px] text-slate-300">
              {deltas.interventions_count} Automated PDX-Engine &amp; ProDocuX Interventions Executed Today
            </span>
          </div>
        </div>

        <div className="flex items-center space-x-6 text-right">
          <div>
            <span className="text-[10px] text-slate-400 block uppercase">Empty Miles Saved</span>
            <span className="text-base font-black text-cyan-300 font-mono">
              -{deltas.empty_miles_saved.toLocaleString()} mi
            </span>
          </div>
          <div>
            <span className="text-[10px] text-slate-400 block uppercase">Detention Secured</span>
            <span className="text-base font-black text-amber-300 font-mono">
              +${deltas.detention_gain_cad.toFixed(2)} CAD
            </span>
          </div>
          <div className="bg-emerald-950/80 border border-emerald-500/50 px-3.5 py-1.5 rounded-lg shadow">
            <span className="text-[10px] text-emerald-400 block uppercase font-bold">Projected Contribution Gain</span>
            <span className="text-xl font-black text-emerald-300 font-mono">
              +${deltas.net_profit_delta_cad.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })} CAD
            </span>
          </div>
        </div>
      </div>

      {/* Comparative Columns: Left (Baseline) vs Right (PDX) */}
      <div className="grid grid-cols-2 gap-4">
        {/* Left Side: Historical Reality Baseline */}
        <div className="bg-slate-950/70 border border-rose-900/50 rounded-xl p-3.5 space-y-3">
          <div className="flex items-center justify-between pb-2 border-b border-rose-900/40">
            <div className="flex items-center space-x-2">
              <span className="w-2.5 h-2.5 rounded-full bg-rose-500"></span>
              <h3 className="text-xs font-black text-rose-300 uppercase tracking-wider">
                🔴 史實基準軌 (Historical Reality)
              </h3>
            </div>
            <span className="text-[10px] bg-rose-950 text-rose-300 border border-rose-800 px-1.5 py-0.5 rounded font-mono">
              Pure Historical Data
            </span>
          </div>

          <div className="space-y-2 text-xs">
            <div className="flex justify-between items-center">
              <span className="text-slate-400">Total Miles Driven:</span>
              <span className="font-mono text-slate-200 font-bold">{baseline.total_miles.toLocaleString()} mi</span>
            </div>

            <div className="flex justify-between items-center bg-rose-950/30 p-1.5 rounded border border-rose-900/30">
              <span className="text-rose-300">Empty Return Miles (Deadhead):</span>
              <span className="font-mono text-rose-400 font-black">
                {baseline.empty_miles.toLocaleString()} mi ({baseline.deadhead_pct}%)
              </span>
            </div>

            <div className="flex justify-between items-center">
              <span className="text-slate-400">Modeled Loaded-Mile Value:</span>
              <span className="font-mono text-slate-200">${baseline.freight_revenue.toLocaleString(undefined, { minimumFractionDigits: 2 })} CAD</span>
            </div>

            <div className="flex justify-between items-center">
              <span className="text-slate-400">Running Cost ($1.85/mi):</span>
              <span className="font-mono text-slate-400">-${baseline.running_cost.toLocaleString(undefined, { minimumFractionDigits: 2 })} CAD</span>
            </div>

            <div className="flex justify-between items-center bg-slate-900 p-1.5 rounded text-[11px]">
              <span className="text-slate-400">Unbilled/Disputed Detention:</span>
              <span className="font-mono text-rose-400">-${baseline.disputed_detention_loss?.toFixed(2) || '0.00'} CAD (Undocumented opportunity)</span>
            </div>

            <div className="flex justify-between items-center pt-2 border-t border-slate-800">
              <span className="text-xs font-bold text-slate-300 uppercase">Cumulative Contribution Margin:</span>
              <span className="text-sm font-mono font-black text-rose-300">
                ${baseline.net_profit.toLocaleString(undefined, { minimumFractionDigits: 2 })} CAD
              </span>
            </div>
          </div>
        </div>

        {/* Right Side: PDX Autonomous Intervention */}
        <div className="bg-slate-950/70 border border-emerald-900/50 rounded-xl p-3.5 space-y-3">
          <div className="flex items-center justify-between pb-2 border-b border-emerald-900/40">
            <div className="flex items-center space-x-2">
              <span className="w-2.5 h-2.5 rounded-full bg-emerald-500 animate-ping"></span>
              <h3 className="text-xs font-black text-emerald-300 uppercase tracking-wider">
                🟢 PDX 智慧介入軌 (PDX Autonomous)
              </h3>
            </div>
            <span className="text-[10px] bg-emerald-950 text-emerald-300 border border-emerald-800 px-1.5 py-0.5 rounded font-mono">
              Engine &amp; Kernel Active
            </span>
          </div>

          <div className="space-y-2 text-xs">
            <div className="flex justify-between items-center">
              <span className="text-slate-400">Total Miles Driven:</span>
              <span className="font-mono text-slate-200 font-bold">{pdx.total_miles.toLocaleString()} mi</span>
            </div>

            <div className="flex justify-between items-center bg-emerald-950/30 p-1.5 rounded border border-emerald-900/30">
              <span className="text-emerald-300">Empty Miles (verified result):</span>
              <span className="font-mono text-emerald-400 font-black">
                {pdx.empty_miles.toLocaleString()} mi ({pdx.deadhead_pct}%)
              </span>
            </div>

            <div className="flex justify-between items-center">
              <span className="text-slate-400">Freight Revenue (verified source only):</span>
              <span className="font-mono text-emerald-300 font-bold">${pdx.freight_revenue.toLocaleString(undefined, { minimumFractionDigits: 2 })} CAD</span>
            </div>

            <div className="flex justify-between items-center">
              <span className="text-slate-400">Running Cost ($1.85/mi):</span>
              <span className="font-mono text-slate-400">-${pdx.running_cost.toLocaleString(undefined, { minimumFractionDigits: 2 })} CAD</span>
            </div>

            <div className="flex justify-between items-center bg-amber-950/30 p-1.5 rounded text-[11px] border border-amber-900/30">
              <span className="text-amber-300">Documented Detention Claims:</span>
              <span className="font-mono text-amber-400 font-bold">+${pdx.recovered_detention_revenue?.toFixed(2) || '0.00'} CAD (Documented claim; collection pending)</span>
            </div>

            <div className="flex justify-between items-center pt-2 border-t border-slate-800">
              <span className="text-xs font-bold text-slate-300 uppercase">Cumulative Contribution Margin:</span>
              <span className="text-base font-mono font-black text-emerald-400">
                ${pdx.net_profit.toLocaleString(undefined, { minimumFractionDigits: 2 })} CAD
              </span>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
};
