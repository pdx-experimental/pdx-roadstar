import React from 'react';

export interface DateOption {
  date: string;
  total_trucks: number;
  total_legs: number;
  empty_legs?: number;
  detention_legs?: number;
}

interface SimControlsBarProps {
  clockStr: string;
  progressPct: number;
  isRunning: boolean;
  speed: number;
  enableStochastic: boolean;
  targetDate: string;
  availableDates: DateOption[];
  fleetSize: number;
  onSelectDate: (d: string) => void;
  onTogglePlay: () => void;
  onChangeSpeed: (s: number) => void;
  onToggleStochastic: () => void;
  onReset: () => void;
  onOpenBenchmark: () => void;
}

export const SimControlsBar: React.FC<SimControlsBarProps> = ({
  clockStr,
  progressPct,
  isRunning,
  speed,
  enableStochastic,
  targetDate,
  availableDates,
  fleetSize,
  onSelectDate,
  onTogglePlay,
  onChangeSpeed,
  onToggleStochastic,
  onReset,
  onOpenBenchmark
}) => {
  const currentIndex = availableDates.findIndex(d => d.date === targetDate);

  const handlePrevDate = () => {
    if (currentIndex > 0) {
      onSelectDate(availableDates[currentIndex - 1].date);
    }
  };

  const handleNextDate = () => {
    if (currentIndex >= 0 && currentIndex < availableDates.length - 1) {
      onSelectDate(availableDates[currentIndex + 1].date);
    }
  };

  return (
    <div className="bg-slate-900 border-b border-slate-800 px-5 py-2.5 flex items-center justify-between shrink-0 shadow-xl text-xs select-none sticky top-0 z-[1000]">
      {/* Left: Branding & Date Selector */}
      <div className="flex items-center space-x-4">
        <div className="flex items-center space-x-2.5">
          <div className="w-8 h-8 rounded-lg bg-gradient-to-br from-cyan-500 to-blue-600 flex items-center justify-center shadow-md">
            <span className="text-white font-black text-sm">🍁</span>
          </div>
          <div>
            <div className="flex items-center space-x-2">
              <h1 className="text-sm font-black tracking-tight text-white">PDX-ROADSTAR THEATER</h1>
              <span className="bg-emerald-950 text-emerald-300 border border-emerald-700 text-[10px] font-mono px-1.5 py-0.5 rounded font-bold">
                {fleetSize} TRUCKS IN SCENARIO
              </span>
            </div>
            <p className="text-[10px] text-slate-400">
              Southern Ontario Freight Corridor · Dataset-Based Scenario Simulator
            </p>
          </div>
        </div>

        {/* Operational Date Dropdown */}
        <div className="flex items-center space-x-1.5 bg-slate-950 p-1 rounded-lg border border-slate-800">
          <button
            onClick={handlePrevDate}
            disabled={currentIndex <= 0}
            className="px-1.5 py-0.5 text-slate-400 hover:text-white disabled:opacity-30 disabled:cursor-not-allowed transition"
            title="Previous Operational Date"
          >
            ◀
          </button>

          <select
            value={targetDate}
            onChange={(e) => onSelectDate(e.target.value)}
            className="bg-slate-900 text-cyan-300 font-mono text-xs font-bold px-2 py-1 rounded border border-slate-700 focus:outline-none focus:border-cyan-500 cursor-pointer"
          >
            {availableDates.map(d => (
              <option key={d.date} value={d.date}>
                {d.date} ({d.total_trucks} trucks · {d.total_legs} legs)
              </option>
            ))}
          </select>

          <button
            onClick={handleNextDate}
            disabled={currentIndex >= availableDates.length - 1}
            className="px-1.5 py-0.5 text-slate-400 hover:text-white disabled:opacity-30 disabled:cursor-not-allowed transition"
            title="Next Operational Date"
          >
            ▶
          </button>
        </div>

        {/* Live Clock Pill & Start Status */}
        <div className="flex items-center space-x-2 bg-slate-950 px-3 py-1.5 rounded-lg border border-slate-800 shadow-inner">
          <span className={`w-2.5 h-2.5 rounded-full ${isRunning ? 'bg-emerald-400 animate-ping' : 'bg-amber-400'}`}></span>
          <span className={`text-[10px] font-bold uppercase tracking-wider ${isRunning ? 'text-emerald-400' : 'text-amber-300'}`}>
            {isRunning ? 'RUNNING' : 'IDLE (CLICK START)'}
          </span>
          <span className="font-mono text-cyan-300 font-black text-xs ml-1">{clockStr || '06:00:00 EST'}</span>
          <span className="text-[10px] text-slate-500 font-mono">({progressPct}%)</span>
        </div>
      </div>

      {/* Center: Day Timeline Progress Bar */}
      <div className="flex-1 max-w-xs mx-4 hidden xl:block">
        <div className="flex justify-between text-[9px] text-slate-400 font-mono mb-0.5">
          <span>06:00 EST</span>
          <span>14:00 Peak</span>
          <span>22:00 Close</span>
        </div>
        <div className="w-full bg-slate-950 h-2 rounded-full overflow-hidden border border-slate-800">
          <div
            className="h-full bg-gradient-to-r from-cyan-500 via-blue-500 to-indigo-500 transition-all duration-300 rounded-full"
            style={{ width: `${progressPct}%` }}
          />
        </div>
      </div>

      {/* Right: Simulation Controls */}
      <div className="flex items-center space-x-2">
        {/* Play/Pause Button */}
        <button
          onClick={onTogglePlay}
          className={`px-4 py-1.5 rounded-lg font-black transition flex items-center space-x-2 shadow-lg cursor-pointer active:scale-95 text-xs ${
            isRunning
              ? 'bg-amber-600 hover:bg-amber-500 text-white shadow-amber-900/30'
              : 'bg-emerald-600 hover:bg-emerald-500 text-white shadow-emerald-900/40 animate-pulse'
          }`}
        >
          <span>{isRunning ? '⏸ Pause' : '▶ Start Simulation'}</span>
        </button>

        {/* Speed Multipliers */}
        <div className="flex items-center space-x-0.5 bg-slate-950 p-1 rounded-lg border border-slate-800">
          {[1, 5, 15, 60].map(s => (
            <button
              key={s}
              onClick={() => onChangeSpeed(s)}
              className={`px-2 py-0.5 rounded text-[10px] font-bold cursor-pointer transition ${
                speed === s ? 'bg-cyan-600 text-white shadow' : 'text-slate-400 hover:text-slate-200'
              }`}
            >
              {s}x
            </button>
          ))}
        </div>

        {/* Stochastic Noise Toggle */}
        <button
          onClick={onToggleStochastic}
          className={`px-2.5 py-1.5 rounded-lg font-bold border transition text-[10px] flex items-center space-x-1 cursor-pointer ${
            enableStochastic
              ? 'bg-purple-950/80 border-purple-600 text-purple-200 shadow-sm'
              : 'bg-slate-950 border-slate-800 text-slate-400 hover:text-slate-200'
          }`}
          title="Toggle stochastic delays and speed jitter"
        >
          <span>🎲 Jitter:</span>
          <span>{enableStochastic ? 'ON' : 'OFF'}</span>
        </button>

        {/* Reset Button */}
        <button
          onClick={onReset}
          className="px-2.5 py-1.5 rounded-lg bg-slate-800 hover:bg-slate-700 text-slate-300 border border-slate-700 font-bold text-[10px] transition cursor-pointer"
        >
          ↺ Reset
        </button>

        {/* Benchmark Button */}
        <button
          onClick={onOpenBenchmark}
          className="bg-indigo-600 hover:bg-indigo-500 text-white font-bold text-xs px-3 py-1.5 rounded-lg border border-indigo-400/40 shadow-sm flex items-center space-x-1 transition cursor-pointer"
        >
          <span>📊 Benchmark</span>
        </button>
      </div>
    </div>
  );
};
