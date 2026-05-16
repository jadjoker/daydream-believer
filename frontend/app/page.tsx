"use client";
import { useState } from "react";
import AIPicks from "@/components/dashboard/AIPicks";
import SimulatorPanel from "@/components/dashboard/SimulatorPanel";
import { TrendingUp, Clock, Rocket, Layers } from "lucide-react";

type Mode = "short" | "long" | "discovery" | "all";

const MODES: { id: Mode; icon: React.ReactNode; label: string; shortLabel: string; title: string; activeCls: string }[] = [
  { id: "short",     icon: <Clock size={12} />,     label: "Short",     shortLabel: "S", title: "Day trading mode",                  activeCls: "bg-cyan-600 text-white" },
  { id: "long",      icon: <TrendingUp size={12} />, label: "Long",      shortLabel: "L", title: "Long-term investing (6–12 months)", activeCls: "bg-purple-600 text-white" },
  { id: "discovery", icon: <Rocket size={12} />,     label: "Discovery", shortLabel: "D", title: "Discovery — next 10-year disruptors", activeCls: "bg-amber-600 text-white" },
  { id: "all",       icon: <Layers size={12} />,     label: "All",       shortLabel: "A", title: "Show all three modes at once",       activeCls: "bg-zinc-600 text-white" },
];

export default function Dashboard() {
  const [mode, setMode] = useState<Mode>("short");
  const [simulatorTicker, setSimulatorTicker] = useState("AAPL");

  const handleTickerSelect = (t: string) => setSimulatorTicker(t);

  return (
    <div className="min-h-screen bg-zinc-950">
      {/* Header */}
      <header className="border-b border-zinc-800 bg-zinc-950/90 backdrop-blur-sm sticky top-0 z-20">
        <div className="max-w-[1600px] mx-auto px-3 py-2.5 flex items-center gap-3 min-w-0">
          {/* Brand */}
          <div className="flex items-center gap-1.5 shrink-0">
            <span className="text-base font-bold text-cyan-400">daydream</span>
            <span className="text-base font-light text-zinc-400 hidden sm:inline">believer</span>
          </div>

          {/* Mode toggle — icon-only on xs, icon+label on sm+ */}
          <div className="flex rounded-lg overflow-hidden border border-zinc-700 shrink-0">
            {MODES.map((m) => (
              <button
                key={m.id}
                onClick={() => setMode(m.id)}
                title={m.title}
                className={`flex items-center gap-1 px-2 sm:px-2.5 py-1.5 text-xs font-semibold transition-colors ${
                  mode === m.id ? m.activeCls : "bg-zinc-800 text-zinc-500 hover:text-zinc-300 active:bg-zinc-700"
                }`}
              >
                {m.icon}
                <span className="hidden sm:inline">{m.label}</span>
                <span className="sm:hidden">{m.shortLabel}</span>
              </button>
            ))}
          </div>

          <div className="text-xs text-zinc-600 hidden lg:block truncate">
            For reference only. Not financial advice.
          </div>
        </div>
      </header>

      {/* Main content */}
      <div className="max-w-[1600px] mx-auto px-3 md:px-4 py-4">
        {mode === "all" ? (
          /* All mode: stacked full-width summaries, simulator below on mobile */
          <div className="grid grid-cols-1 lg:grid-cols-[3fr_2fr] gap-4 items-start">
            <AIPicks
              onTickerSelect={handleTickerSelect}
              onSimulate={handleTickerSelect}
              mode="all"
            />
            <SimulatorPanel ticker={simulatorTicker} />
          </div>
        ) : (
          <div className="grid grid-cols-1 lg:grid-cols-[3fr_2fr] gap-4 items-start">
            <AIPicks
              onTickerSelect={handleTickerSelect}
              onSimulate={handleTickerSelect}
              mode={mode}
            />
            <SimulatorPanel ticker={simulatorTicker} />
          </div>
        )}
      </div>
    </div>
  );
}
