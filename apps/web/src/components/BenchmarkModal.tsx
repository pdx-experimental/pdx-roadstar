import React, { useEffect, useState } from 'react';

interface BenchmarkModalProps {
  isOpen: boolean;
  onClose: () => void;
}

interface BenchmarkData {
  region: string;
  target_date: string;
  provisional: boolean;
  dataset_scope: {
    total_orders_on_day: number;
    total_freight_miles: number;
    corridor_coverage: string;
  };
  baseline_manual: {
    deadhead_ratio_pct: number;
    wasted_empty_miles: number;
    modeled_empty_mile_cost_cad: number;
    unbilled_detention_hours: number;
    modeled_freight_value_cad: number;
    modeled_operating_cost_cad: number;
    contribution_margin_cad: number;
  };
  with_pdx_optimization: {
    deadhead_ratio_pct: number;
    empty_miles_saved: number;
    modeled_fuel_cost_savings_cad: number;
    source_backhaul_revenue_cad: number;
    documented_detention_claim_cad: number;
    projected_contribution_delta_cad: number;
    projected_contribution_margin_cad: number;
  };
  backhaul_data_status: { revenue_eligible: boolean; reason: string };
  notes: string[];
}

export const BenchmarkModal: React.FC<BenchmarkModalProps> = ({ isOpen, onClose }) => {
  const [data, setData] = useState<BenchmarkData | null>(null);
  const [loading, setLoading] = useState<boolean>(false);

  useEffect(() => {
    if (!isOpen) return;
    setLoading(true);
    fetch('/api/analysis/benchmark')
      .then((res) => res.json())
      .then((json: BenchmarkData) => {
        setData(json);
        setLoading(false);
      })
      .catch((err) => {
        console.error('Failed to load benchmark analysis:', err);
        setLoading(false);
      });
  }, [isOpen]);

  if (!isOpen) return null;

  return (
    <div className="fixed inset-0 z-[9999] flex items-center justify-center bg-black/80 backdrop-blur-sm p-4 animate-fadeIn">
      <div className="bg-slate-900 border border-slate-700 rounded-2xl w-full max-w-3xl max-h-[90vh] flex flex-col shadow-2xl overflow-hidden text-xs">
        {/* Header */}
        <div className="bg-gradient-to-r from-slate-900 via-slate-800 to-slate-900 p-5 border-b border-slate-800 flex items-center justify-between">
          <div className="flex items-center space-x-3">
            <span className="text-2xl">📊</span>
            <div>
              <div className="flex items-center space-x-2">
                <h2 className="text-base font-extrabold text-white tracking-wide">
                  SCENARIO CONTRIBUTION COMPARISON
                </h2>
                {data?.provisional && (
                  <span className="bg-amber-950 text-amber-300 border border-amber-800 text-[10px] px-2 py-0.5 rounded font-mono font-bold">
                    PROVISIONAL (RUN IN PROGRESS)
                  </span>
                )}
              </div>
              <p className="text-xs text-slate-400">
                Scenario Component Accounting · Date: <span className="font-mono text-cyan-300">{data?.target_date || '2026-08-14'}</span> · {data?.region || 'Southern Ontario Corridor'}
              </p>
            </div>
          </div>
          <button
            onClick={onClose}
            className="text-slate-400 hover:text-white bg-slate-800 hover:bg-slate-700 p-1.5 rounded-lg text-sm transition cursor-pointer"
          >
            ✕ Close
          </button>
        </div>

        {/* Content */}
        <div className="p-6 overflow-y-auto space-y-6 text-slate-200">
          {loading || !data ? (
            <div className="py-12 text-center text-slate-400 font-mono">Loading verified benchmark data...</div>
          ) : (
            <>
              {/* Data Profile Overview */}
              <div className="grid grid-cols-4 gap-3">
                <div className="bg-slate-950 p-3 rounded-xl border border-slate-800">
                  <span className="text-[11px] text-slate-400 block font-bold">Corridor Dispatched Legs:</span>
                  <span className="text-lg font-black text-white font-mono">{data.dataset_scope.total_orders_on_day} Legs</span>
                  <span className="text-[10px] text-cyan-400 block mt-0.5">{data.target_date}</span>
                </div>
                <div className="bg-slate-950 p-3 rounded-xl border border-slate-800">
                  <span className="text-[11px] text-slate-400 block font-bold">Total Corridor Miles:</span>
                  <span className="text-lg font-black text-white font-mono">{data.dataset_scope.total_freight_miles.toLocaleString(undefined, { maximumFractionDigits: 1 })} mi</span>
                  <span className="text-[10px] text-slate-400 block mt-0.5">Identical Traversal</span>
                </div>
                <div className="bg-slate-950 p-3 rounded-xl border border-slate-800">
                  <span className="text-[11px] text-slate-400 block font-bold">Empty Miles Converted:</span>
                  <span className="text-lg font-black text-emerald-400 font-mono">{data.with_pdx_optimization.empty_miles_saved.toLocaleString(undefined, { maximumFractionDigits: 1 })} mi</span>
                  <span className="text-[10px] text-emerald-300/80 block mt-0.5">Deadhead Reduction</span>
                </div>
                <div className="bg-slate-950 p-3 rounded-xl border border-slate-800">
                  <span className="text-[11px] text-slate-400 block font-bold">Unbilled Dwell Hours:</span>
                  <span className="text-lg font-black text-amber-400 font-mono">{data.baseline_manual.unbilled_detention_hours.toFixed(1)} hrs</span>
                  <span className="text-[10px] text-amber-300/80 block mt-0.5">Tariff: $95/hr</span>
                </div>
              </div>

              {/* Comparison Side by Side */}
              <div className="grid grid-cols-2 gap-4">
                {/* Traditional Manual Dispatch */}
                <div className="bg-rose-950/20 border border-rose-900/60 rounded-xl p-4 space-y-3">
                  <div className="flex items-center space-x-2 border-b border-rose-900/40 pb-2">
                    <span className="text-base">❌</span>
                    <h3 className="font-bold text-rose-300 uppercase tracking-wider text-xs">
                      Baseline (Manual Dispatch &amp; Paper Invoicing)
                    </h3>
                  </div>
                  <ul className="space-y-2 text-[11px] text-slate-300">
                    <li className="flex justify-between">
                      <span className="text-slate-400">Empty Deadhead Ratio:</span>
                      <span className="font-bold text-rose-400 font-mono">{data.baseline_manual.deadhead_ratio_pct.toFixed(1)}% ({data.baseline_manual.wasted_empty_miles.toLocaleString(undefined, { maximumFractionDigits: 1 })} mi)</span>
                    </li>
                    <li className="flex justify-between">
                      <span className="text-slate-400">Running Cost ($1.85/mi):</span>
                      <span className="font-bold text-rose-400 font-mono">-${(data.dataset_scope.total_freight_miles * 1.85).toLocaleString(undefined, { maximumFractionDigits: 2 })} CAD</span>
                    </li>
                    <li className="flex justify-between">
                      <span className="text-slate-400">Unbilled Detention Opportunity:</span>
                      <span className="font-bold text-rose-400 font-mono">-${(data.baseline_manual.unbilled_detention_hours * 95).toLocaleString(undefined, { maximumFractionDigits: 2 })} CAD</span>
                    </li>
                    <li className="flex justify-between">
                      <span className="text-slate-400">Modeled Loaded-Mile Value:</span>
                      <span className="font-bold text-white font-mono">${data.baseline_manual.modeled_freight_value_cad.toLocaleString(undefined, { maximumFractionDigits: 2 })} CAD</span>
                    </li>
                    <li className="flex justify-between border-t border-rose-900/40 pt-2">
                      <span className="text-slate-300 font-bold">Modeled Contribution Margin:</span>
                      <span className="font-bold text-white font-mono">${data.baseline_manual.contribution_margin_cad.toLocaleString(undefined, { maximumFractionDigits: 2 })} CAD</span>
                    </li>
                  </ul>
                </div>

                {/* With PDX & ProDocuX */}
                <div className="bg-emerald-950/20 border border-emerald-900/60 rounded-xl p-4 space-y-3">
                  <div className="flex items-center space-x-2 border-b border-emerald-900/40 pb-2">
                    <span className="text-base">✅</span>
                    <h3 className="font-bold text-emerald-300 uppercase tracking-wider text-xs">
                      With PDX-Artifact-Engine &amp; ProDocuX
                    </h3>
                  </div>
                  <ul className="space-y-2 text-[11px] text-slate-300">
                    <li className="flex justify-between">
                      <span className="text-slate-400">Empty Deadhead Ratio:</span>
                      <span className="font-bold text-emerald-400 font-mono">{data.with_pdx_optimization.deadhead_ratio_pct.toFixed(1)}% ({data.with_pdx_optimization.empty_miles_saved.toLocaleString(undefined, { maximumFractionDigits: 1 })} mi converted)</span>
                    </li>
                    <li className="flex justify-between">
                      <span className="text-slate-400">Fuel Cost Savings:</span>
                      <span className="font-bold text-slate-400 font-mono">$0.00 CAD (Same Mileage)</span>
                    </li>
                    <li className="flex justify-between">
                      <span className="text-slate-400">Source-Priced Backhaul:</span>
                      <span className="font-bold text-indigo-300 font-mono">+${data.with_pdx_optimization.source_backhaul_revenue_cad.toLocaleString(undefined, { maximumFractionDigits: 2 })} CAD</span>
                    </li>
                    <li className="flex justify-between">
                      <span className="text-slate-400">Documented Claim (Collection Pending):</span>
                      <span className="font-bold text-cyan-300 font-mono">+${data.with_pdx_optimization.documented_detention_claim_cad.toLocaleString(undefined, { maximumFractionDigits: 2 })} CAD</span>
                    </li>
                    <li className="flex justify-between border-t border-emerald-900/40 pt-2">
                      <span className="text-slate-300 font-bold">Projected Contribution Margin:</span>
                      <span className="font-bold text-emerald-300 font-mono">${data.with_pdx_optimization.projected_contribution_margin_cad.toLocaleString(undefined, { maximumFractionDigits: 2 })} CAD</span>
                    </li>
                  </ul>
                </div>
              </div>

              {/* Bottom Net ROI Highlight */}
              <div className="bg-gradient-to-r from-cyan-950/80 via-blue-950/80 to-emerald-950/80 border border-cyan-700/80 rounded-xl p-4 flex items-center justify-between shadow-xl">
                <div>
                  <span className="text-xs font-bold text-cyan-300 uppercase tracking-wider block">
                    Projected Scenario Contribution Delta:
                  </span>
                  <span className="text-[11px] text-slate-400 font-mono">
                    Source Backhaul (${data.with_pdx_optimization.source_backhaul_revenue_cad.toLocaleString(undefined, { maximumFractionDigits: 2 })}) + Documented Claim (${data.with_pdx_optimization.documented_detention_claim_cad.toLocaleString(undefined, { maximumFractionDigits: 2 })}) − Added Cost
                  </span>
                </div>
                <div className="text-right">
                  <span className="text-2xl font-black text-emerald-300 font-mono">+${data.with_pdx_optimization.projected_contribution_delta_cad.toLocaleString(undefined, { maximumFractionDigits: 2 })} CAD</span>
                  <span className="text-[10px] text-cyan-300 block font-mono">No annual extrapolation · documented claims are not cash receipts</span>
                </div>
              </div>

              {/* Methodological Notes */}
              <div className="bg-slate-950 border border-slate-800/80 rounded-xl p-3 text-[10px] text-slate-400 space-y-1">
                <span className="font-bold text-slate-300 uppercase block tracking-wider text-[9px]">Methodological Governance &amp; Gate E Accounting Compliance:</span>
                {data.notes.map((note, idx) => (
                  <p key={idx} className="flex items-start space-x-1.5">
                    <span className="text-cyan-400">ℹ</span>
                    <span>{note}</span>
                  </p>
                ))}
              </div>
            </>
          )}
        </div>

        {/* Footer */}
        <div className="bg-slate-950 p-4 border-t border-slate-800 flex items-center justify-between">
          <span className="text-[11px] text-slate-500 font-mono">
            Dataset scenario: {data?.dataset_scope.total_orders_on_day || 0} scheduled legs · modeled values are identified above
          </span>
          <button
            onClick={onClose}
            className="px-4 py-1.5 bg-cyan-600 hover:bg-cyan-500 text-white font-bold text-xs rounded-lg transition cursor-pointer"
          >
            Got It
          </button>
        </div>
      </div>
    </div>
  );
};
