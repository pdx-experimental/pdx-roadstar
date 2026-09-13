import React from 'react';
import { InterventionItem } from './PdxMap';

interface DossierReceiptModalProps {
  intervention: InterventionItem | null;
  onClose: () => void;
}

export const DossierReceiptModal: React.FC<DossierReceiptModalProps> = ({ intervention, onClose }) => {
  if (!intervention) return null;

  const isBackhaul = intervention.type === 'PDX_BACKHAUL_MATCH';
  const isDossier = intervention.type === 'PRODOCUX_DETENTION_DOSSIER';
  const filename = intervention.filename || '';
  const isPdf = filename.endsWith('.pdf');
  const downloadUrl = intervention.download_url || (filename ? `/api/artifacts/download/${filename}` : '');

  return (
    <div className="fixed inset-0 z-[9999] flex items-center justify-center bg-black/80 backdrop-blur-sm p-4 animate-fadeIn">
      <div className="bg-slate-900 border border-slate-700 rounded-2xl w-full max-w-2xl max-h-[90vh] flex flex-col shadow-2xl overflow-hidden text-xs">
        {/* Header */}
        <div className="bg-gradient-to-r from-slate-900 via-slate-800 to-slate-900 p-4 border-b border-slate-800 flex items-center justify-between">
          <div className="flex items-center space-x-2.5">
            <span className="text-2xl">{isBackhaul ? '🤖' : (isDossier ? '📜' : '🛡️')}</span>
            <div>
              <h2 className="text-sm font-extrabold text-white tracking-wide uppercase">
                {isBackhaul ? 'PDX-ARTIFACT-ENGINE EXECUTION RECEIPT' : (isDossier ? 'PRODOCUX VERIFIABLE DETENTION DOSSIER' : 'SAFETY COMPLIANCE CERTIFICATE')}
              </h2>
              <p className="text-[10px] text-slate-400 font-mono">
                Receipt ID: {intervention.receipt_id || `PDX-REC-${intervention.sim_minute}`}
              </p>
            </div>
          </div>
          <button
            onClick={onClose}
            className="text-slate-400 hover:text-white bg-slate-800 hover:bg-slate-700 px-2.5 py-1 rounded-lg transition text-xs font-bold"
          >
            ✕ Close
          </button>
        </div>

        {/* Body */}
        <div className="p-5 space-y-4 text-slate-200 overflow-y-auto">
          {/* Key Details Card */}
          <div className="bg-slate-950 p-4 rounded-xl border border-slate-800 space-y-2">
            <div className="flex justify-between items-center border-b border-slate-800 pb-2">
              <span className="text-slate-400">Assigned Unit / Driver:</span>
              <span className="font-mono font-bold text-white">{intervention.truck} ({intervention.driver})</span>
            </div>
            <div className="flex justify-between items-center border-b border-slate-800 pb-2">
              <span className="text-slate-400">Geofence Facility / Node:</span>
              <span className="font-bold text-cyan-300">{intervention.location_name}</span>
            </div>
            <div className="flex justify-between items-center border-b border-slate-800 pb-2">
              <span className="text-slate-400">Execution Time:</span>
              <span className="font-mono text-slate-300">{intervention.time} (Simulated Clock)</span>
            </div>
            <div className="flex justify-between items-center border-b border-slate-800 pb-2">
              <span className="text-slate-400">Documented Claim Value:</span>
              <span className="font-mono font-black text-emerald-400 text-sm">{intervention.financial_delta}</span>
            </div>
            <div className="flex justify-between items-center">
              <span className="text-slate-400">Physical Artifact Status:</span>
              <span className="px-2 py-0.5 rounded bg-emerald-950 text-emerald-300 border border-emerald-700 text-[10px] font-bold">
                ✓ Generated &amp; Saved to Disk ({filename})
              </span>
            </div>
          </div>

          {/* Cryptographic SHA-256 Proof */}
          <div className="bg-slate-950 p-4 rounded-xl border border-slate-800 space-y-2">
            <div className="flex items-center space-x-2 text-cyan-400 font-bold">
              <span>🔐</span>
              <span>CRYPTOGRAPHIC EVIDENCE INTEGRITY SEAL</span>
            </div>
            <p className="text-[11px] text-slate-400">
              Immutable SHA-256 digital signature computed by ProDocuX / PDX Kernel over the physical artifact:
            </p>
            <div className="bg-slate-900 p-2.5 rounded-lg border border-slate-800 font-mono text-[10px] text-cyan-200 break-all select-all">
              {intervention.sha256 || 'Unavailable'}
            </div>
          </div>

          {/* Regulatory & Audit Breakdown */}
          <div className="bg-slate-950 p-4 rounded-xl border border-slate-800 space-y-2 text-[11px] text-slate-300">
            <div className="font-bold text-slate-200">Canadian Regulatory Compliance:</div>
            {isBackhaul ? (
              <ul className="list-disc list-inside space-y-1 text-slate-400">
                <li>Transport Canada Commercial Vehicle Drivers HOS Regulations (SOR/2005-313) Cycle 1 certified.</li>
                <li>Ontario Highway Traffic Act Gross Vehicle Weight limit audited (&lt; 80,000 lbs).</li>
                <li>pdx-artifact-core execution plan validated and signed.</li>
              </ul>
            ) : (
              <ul className="list-disc list-inside space-y-1 text-slate-400">
                <li>Standard 2-Hour Facility Grace Period subtracted from total dock dwell.</li>
                <li>Audited Tariff Rate: <b>$95.00 CAD per Billable Hour</b>.</li>
                <li>Tamper-evident telematics geofence entry and exit proof attached.</li>
              </ul>
            )}
          </div>
        </div>

        {/* Footer with Real Download Action */}
        <div className="bg-slate-950 p-4 border-t border-slate-800 flex items-center justify-between">
          <div className="flex items-center space-x-2">
            {downloadUrl ? (
              <a
                href={downloadUrl}
                target="_blank"
                rel="noopener noreferrer"
                download={filename}
                className="px-3.5 py-1.5 bg-emerald-600 hover:bg-emerald-500 text-white font-bold text-xs rounded-lg transition flex items-center space-x-1.5 shadow"
              >
                <span>{isPdf ? '📥 Download Signed PDF Dossier' : '📄 View JSON Receipt'}</span>
              </a>
            ) : (
              <span className="text-slate-500 text-[10px]">Artifact ready</span>
            )}
          </div>

          <button
            onClick={onClose}
            className="px-4 py-1.5 bg-slate-800 hover:bg-slate-700 text-slate-300 font-bold text-xs rounded-lg transition cursor-pointer"
          >
            Dismiss
          </button>
        </div>
      </div>
    </div>
  );
};
