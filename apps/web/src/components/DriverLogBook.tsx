import React from 'react';

interface DriverHOSProps {
  hos: {
    driver_id: number;
    first_name: string;
    current_duty: number;
    duty_status_desc: string;
    remaining_hours_can_7: number;
    remaining_hours_can_14: number;
    shift_driving_hours: number;
    shift_on_duty_hours: number;
    shift_elapsed_hours: number;
    is_compliant: boolean;
    violations: string[];
  } | null;
}

export const DriverLogBook: React.FC<DriverHOSProps> = ({ hos }) => {
  if (!hos) return null;

  const drivePct = Math.min(100, (hos.shift_driving_hours / 13.0) * 100);
  const onDutyPct = Math.min(100, (hos.shift_on_duty_hours / 14.0) * 100);
  const cyclePct = Math.max(0, (hos.remaining_hours_can_7 / 70.0) * 100);

  return (
    <div className="bg-slate-900 border border-slate-800 rounded-xl p-4 shadow-xl">
      <div className="flex items-center justify-between pb-2 mb-3 border-b border-slate-800">
        <div className="flex items-center space-x-2">
          <span className="text-xl">📋</span>
          <div>
            <h3 className="text-xs font-bold text-white tracking-wide">CANADIAN ELD DRIVER LOGBOOK (RODS)</h3>
            <p className="text-[10px] text-slate-400">Transport Canada South of 60°N Regulations</p>
          </div>
        </div>
        <span className={`text-[10px] font-bold px-2 py-0.5 rounded ${
          hos.is_compliant ? 'bg-emerald-950 text-emerald-300 border border-emerald-800' : 'bg-rose-950 text-rose-300 border border-rose-800'
        }`}>
          {hos.is_compliant ? '✓ 100% HOS COMPLIANT' : '⚠️ VIOLATION DETECTED'}
        </span>
      </div>

      {/* Driver Header */}
      <div className="flex items-center justify-between text-xs mb-3">
        <div className="text-slate-300 font-semibold">
          Driver: <span className="text-white font-bold">{hos.first_name}</span> (ID: {hos.driver_id})
        </div>
        <div className="bg-slate-800 px-2.5 py-0.5 rounded text-cyan-300 font-mono text-[11px]">
          Status: {hos.duty_status_desc}
        </div>
      </div>

      {/* Clocks Progress */}
      <div className="space-y-2 text-xs">
        <div>
          <div className="flex justify-between text-[11px] mb-1">
            <span className="text-slate-400">13-Hour Driving Limit:</span>
            <span className="font-bold text-white">{hos.shift_driving_hours.toFixed(1)} / 13.0 h</span>
          </div>
          <div className="w-full bg-slate-950 rounded-full h-2 overflow-hidden border border-slate-800">
            <div
              className={`h-full rounded-full transition-all ${drivePct > 85 ? 'bg-rose-500' : 'bg-cyan-500'}`}
              style={{ width: `${drivePct}%` }}
            />
          </div>
        </div>

        <div>
          <div className="flex justify-between text-[11px] mb-1">
            <span className="text-slate-400">14-Hour On-Duty Limit:</span>
            <span className="font-bold text-white">{hos.shift_on_duty_hours.toFixed(1)} / 14.0 h</span>
          </div>
          <div className="w-full bg-slate-950 rounded-full h-2 overflow-hidden border border-slate-800">
            <div
              className={`h-full rounded-full transition-all ${onDutyPct > 85 ? 'bg-rose-500' : 'bg-purple-500'}`}
              style={{ width: `${onDutyPct}%` }}
            />
          </div>
        </div>

        <div>
          <div className="flex justify-between text-[11px] mb-1">
            <span className="text-slate-400">Cycle 1 Remaining (70h/7d):</span>
            <span className="font-bold text-emerald-400">{hos.remaining_hours_can_7.toFixed(1)} h Remaining</span>
          </div>
          <div className="w-full bg-slate-950 rounded-full h-2 overflow-hidden border border-slate-800">
            <div
              className="h-full rounded-full bg-emerald-500 transition-all"
              style={{ width: `${cyclePct}%` }}
            />
          </div>
        </div>
      </div>

      {hos.violations.length > 0 && (
        <div className="mt-3 p-2 bg-rose-950/60 border border-rose-800 rounded text-[10px] text-rose-300 space-y-0.5">
          {hos.violations.map((v, i) => (
            <div key={i}>⚠️ {v}</div>
          ))}
        </div>
      )}
    </div>
  );
};
