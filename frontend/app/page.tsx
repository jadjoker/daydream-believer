"use client";
import { useState } from "react";
import AIPicks from "@/components/dashboard/AIPicks";
import SimulatorPanel from "@/components/dashboard/SimulatorPanel";
import { TrendingUp, Clock, Rocket } from "lucide-react";

type Mode = "short" | "long" | "discovery";

export default function Dashboard() {
  const [mode, setMode] = useState<Mode>("short");
  const [simulatorTicker, setSimulatorTicker] = useState("AAPL");

  const handleTickerSelect = (t: string) => setSimulatorTicker(t);

  return (
    <div className="min-h-screen bg-zinc-950">
      {/* Header */}
      <header className="border-b border-zinc-800 bg-zinc-950/90 backdrop-blur-sm sticky top-0 z-20">
        <div className="max-w-[1600px] mx-auto px-3 py-3 flex items-center gap-4">
          <div className="flex items-center gap-2 shrink-0">
            <span className="text-lg font-bold text-cyan-400">daydream</span>
            <span className="text-lg font-light text-zinc-400 hidden sm:inline">believer</span>
          </div>

          {/* Mode toggle */}
          <div className="flex rounded-lg overflow-hidden border border-zinc-700 shrink-0">
            <button
              onClick={() => setMode("short")}
              className={`flex items-center gap-1 px-2.5 py-1.5 text-xs font-semibold transition-colors ${
                mode === "short" ? "bg-cyan-600 text-white" : "bg-zinc-800 text-zinc-500 hover:text-zinc-300"
              }`}
              title="Day trading mode"
            >
              <Clock size={11} /> Short
            </button>
            <button
              onClick={() => setMode("long")}
              className={`flex items-center gap-1 px-2.5 py-1.5 text-xs font-semibold transition-colors ${
                mode === "long" ? "bg-purple-600 text-white" : "bg-zinc-800 text-zinc-500 hover:text-zinc-300"
              }`}
              title="Long-term investing mode (6–12 months)"
            >
              <TrendingUp size={11} /> Long
            </button>
            <button
              onClick={() => setMode("discovery")}
              className={`flex items-center gap-1 px-2.5 py-1.5 text-xs font-semibold transition-colors ${
                mode === "discovery" ? "bg-amber-600 text-white" : "bg-zinc-800 text-zinc-500 hover:text-zinc-300"
              }`}
              title="Discovery mode — next 10-year disruptors"
            >
              <Rocket size={11} /> Discovery
            </button>
          </div>

          <div className="text-xs text-zinc-600 hidden md:block">
            For reference only. Not financial advice.
          </div>
        </div>
      </header>

      {/* Main content */}
      <div className="max-w-[1600px] mx-auto px-3 md:px-4 py-4">
        <div className="grid grid-cols-1 lg:grid-cols-[3fr_2fr] gap-4 items-start">
          <AIPicks
            onTickerSelect={handleTickerSelect}
            onSimulate={handleTickerSelect}
            mode={mode}
          />
          <SimulatorPanel ticker={simulatorTicker} />
        </div>
      </div>
    </div>
  );
}
