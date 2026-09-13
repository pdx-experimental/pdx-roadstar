import React from 'react';

interface InterventionEvent {
  time: string;
  sim_minute: number;
  type: string;
  truck: string;
  driver: string;
  desc: string;
  financial_delta: string;
}

interface InterventionStreamProps {
  interventions: InterventionEvent[];
}

export const InterventionStream: React.FC<InterventionStreamProps> = ({ interventions }) => {
  return (
    <div className="bg-slate-900 border border-slate-800 rounded-xl p-4 flex flex-col h-full shadow-xl">
      <div className="flex items-center justify-between pb-2.5 border-b border-slate-800 shrink-0">
        <div className="flex items-center space-x-2">
          <span className="text-lg">⚡</span>
          <div>
            <h2 className="text-xs font-bold text-white tracking-wide uppercase">
              PDX SYSTEM INTERVENTION FEED (即時介入點事件流)
            </h2>
            <p className="text-[10px] text-slate-400">
              Capturing automated actions by pdx-artifact-engine &amp; prodocux kernel
            </p>
          </div>
        </div>
        <span className="text-[10px] font-mono bg-cyan-950 text-cyan-300 border border-cyan-800 px-2 py-0.5 rounded font-bold">
          {interventions.length} Interventions
        </span>
      </div>

      {/* Stream List */}
      <div className="my-2.5 flex-1 overflow-y-auto space-y-2 pr-1">
        {interventions.length === 0 ? (
          <div className="text-center py-12 text-slate-500 text-xs">
            <span className="text-2xl block mb-2">⏳</span>
            Simulation starting at 06:00 EST. As trucks reach destinations and dock thresholds, automated PDX intervention points will appear here.
          </div>
        ) : (
          interventions.map((evt, idx) => {
            const isBackhaul = evt.type === 'PDX_BACKHAUL_MATCH';
            const isDetention = evt.type === 'PRODOCUX_DETENTION_DOSSIER';

            return (
              <div
                key={idx}
                className={`p-2.5 rounded-lg border transition animate-fadeIn ${
                  isBackhaul ? 'bg-cyan-950/25 border-cyan-800/80 shadow-sm' :
                  isDetention ? 'bg-amber-950/25 border-amber-800/80 shadow-sm' :
                  'bg-purple-950/25 border-purple-800/80'
                }`}
              >
                <div className="flex items-center justify-between text-[11px] mb-1">
                  <div className="flex items-center space-x-1.5">
                    <span className="font-mono text-slate-400 font-bold">[{evt.time.slice(0, 5)}]</span>
                    <span className={`px-1.5 py-0.2 rounded font-mono text-[9px] font-black uppercase ${
                      isBackhaul ? 'bg-cyan-900 text-cyan-200' :
                      isDetention ? 'bg-amber-900 text-amber-200' :
                      'bg-purple-900 text-purple-200'
                    }`}>
                      {isBackhaul ? '⚡ PDX-Engine' : isDetention ? '📜 ProDocuX' : '🛡️ HOS-Audit'}
                    </span>
                    <span className="text-slate-200 font-semibold">{evt.truck}</span>
                  </div>
                  <span className="font-mono text-emerald-400 font-black text-xs">
                    {evt.financial_delta}
                  </span>
                </div>

                <p className="text-[11px] text-slate-300 pl-1 leading-relaxed">
                  {evt.desc}
                </p>
              </div>
            );
          })
        )}
      </div>
    </div>
  );
};
