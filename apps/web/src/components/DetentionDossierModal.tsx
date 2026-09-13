import React, { useState } from 'react';

interface DetentionRecord {
  record_id: string;
  trip_number: string;
  bill_number: string;
  driver_id: number;
  driver_name: string;
  facility_id: string;
  facility_name: string;
  geofence_arrival_time: string;
  free_time_hours: number;
  total_wait_hours: number;
  billable_hours: number;
  hourly_rate_cad: number;
  total_detention_fee_cad: number;
  status: string;
  dossier_sha256?: string;
  dossier_filename?: string;
}

interface DetentionDossierModalProps {
  records: DetentionRecord[];
  onGenerateDossier: (recordId: string) => Promise<any>;
}

export const DetentionDossierModal: React.FC<DetentionDossierModalProps> = ({
  records,
  onGenerateDossier
}) => {
  const [loadingId, setLoadingId] = useState<string | null>(null);
  const [successDossier, setSuccessDossier] = useState<any | null>(null);

  const handleGenerate = async (recordId: string) => {
    setLoadingId(recordId);
    try {
      const res = await onGenerateDossier(recordId);
      setSuccessDossier(res);
    } catch (err) {
      console.error(err);
    } finally {
      setLoadingId(null);
    }
  };

  return (
    <div className="bg-slate-900 border border-slate-800 rounded-xl p-4 flex flex-col h-full shadow-xl">
      <div className="flex items-center justify-between pb-3 border-b border-slate-800">
        <div className="flex items-center space-x-2">
          <span className="text-xl">⏱️</span>
          <div>
            <h2 className="text-sm font-bold text-white tracking-wide">DETENTION AUTOMATED BILLING &amp; DOSSIER</h2>
            <p className="text-[11px] text-slate-400">ProDocuX Kernel 0.3.0rc4 · Deterministic Evidence Receipt with SHA-256 Identity</p>
          </div>
        </div>
        <span className="text-xs font-mono bg-rose-950 text-rose-300 border border-rose-800 px-2 py-0.5 rounded">
          &gt; 2h Threshold
        </span>
      </div>

      {/* Records List */}
      <div className="my-3 flex-1 overflow-y-auto space-y-2.5 pr-1">
        {records.length === 0 ? (
          <div className="text-center py-8 text-slate-500 text-xs">
            No trucks currently held at docks beyond the 2-hour free threshold.
          </div>
        ) : (
          records.map(r => {
            const isBillable = r.total_wait_hours > 2.0;
            return (
              <div
                key={r.record_id}
                className={`p-3 rounded-lg border transition ${
                  isBillable ? 'bg-rose-950/20 border-rose-800/80 shadow-sm' : 'bg-slate-950 border-slate-800'
                }`}
              >
                <div className="flex items-center justify-between mb-1.5">
                  <div className="flex items-center space-x-2">
                    <span className={`w-2 h-2 rounded-full ${isBillable ? 'bg-rose-500 animate-ping' : 'bg-amber-500'}`}></span>
                    <span className="text-xs font-bold text-white">{r.facility_name}</span>
                  </div>
                  <span className="text-[11px] font-mono font-bold text-rose-400">
                    ${r.total_detention_fee_cad.toFixed(2)} CAD
                  </span>
                </div>

                <div className="grid grid-cols-3 gap-2 text-[11px] text-slate-300 my-2 bg-slate-900/60 p-2 rounded">
                  <div>
                    <span className="text-slate-500 block">Total Dwell Time:</span>
                    <span className="font-bold text-white">{r.total_wait_hours.toFixed(1)} Hours</span>
                  </div>
                  <div>
                    <span className="text-slate-500 block">Free Time:</span>
                    <span className="text-slate-400">2.0 Hours</span>
                  </div>
                  <div>
                    <span className="text-slate-500 block">Billable Hours:</span>
                    <span className="font-bold text-rose-400">{r.billable_hours.toFixed(1)} Hours</span>
                  </div>
                </div>

                <div className="flex items-center justify-between pt-2 border-t border-slate-800/80">
                  <div className="text-[10px] text-slate-400">
                    BOL #{r.bill_number} · Driver: {r.driver_name}
                  </div>

                  <button
                    onClick={() => handleGenerate(r.record_id)}
                    disabled={loadingId === r.record_id}
                    className="bg-rose-600 hover:bg-rose-500 text-white text-[11px] font-bold px-3 py-1.5 rounded transition shadow flex items-center space-x-1"
                  >
                    {loadingId === r.record_id ? (
                      <span>⚙️ Assembling...</span>
                    ) : (
                      <span>📜 Generate ProDocuX Dossier</span>
                    )}
                  </button>
                </div>
              </div>
            );
          })
        )}
      </div>

      {/* Download Banner if dossier was generated */}
      {successDossier && (
        <div className="mt-2 p-3 bg-slate-950 border border-cyan-800 rounded-lg text-xs space-y-2">
          <div className="flex items-center justify-between text-cyan-300 font-bold">
            <span>✓ Deterministic Dossier Ready</span>
            <span className="text-[10px] font-mono text-slate-400">SHA-256 Verified</span>
          </div>
          <div className="font-mono text-[10px] text-slate-400 truncate bg-slate-900 p-1.5 rounded">
            Hash: {successDossier.sha256}
          </div>
          <div className="flex items-center justify-between">
            <span className="text-slate-300 font-semibold">Total Invoiced: ${successDossier.total_fee_cad.toFixed(2)} CAD</span>
            <a
              href={successDossier.download_url}
              target="_blank"
              rel="noreferrer"
              className="bg-cyan-600 hover:bg-cyan-500 text-white font-bold text-[11px] px-3 py-1 rounded transition shadow inline-flex items-center space-x-1"
            >
              <span>⬇️ Download PDF Invoice</span>
            </a>
          </div>
        </div>
      )}
    </div>
  );
};
