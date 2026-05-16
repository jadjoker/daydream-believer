"use client";
import AIPicks from "@/components/dashboard/AIPicks";
import SimulatorPanel from "@/components/dashboard/SimulatorPanel";
import { useState } from "react";

export default function Dashboard() {
  const [simulatorTicker, setSimulatorTicker] = useState("AAPL");

  return (
    <div className="min-h-screen bg-zinc-950">
      {/* Header */}
      <header className="border-b border-zinc-800 bg-zinc-950/90 backdrop-blur-sm sticky top-0 z-20">
        <div className="max-w-[1600px] mx-auto px-3 py-2.5 flex items-center gap-3">
          <span className="text-base font-bold text-cyan-400">daydream</span>
          <span className="text-base font-light text-zinc-400 hidden sm:inline">believer</span>
          <div className="text-xs text-zinc-600 hidden lg:block ml-2">
            For reference only. Not financial advice.
          </div>
        </div>
      </header>

      {/* Main content */}
      <div className="max-w-[1600px] mx-auto px-3 md:px-4 py-4">
        <div className="grid grid-cols-1 lg:grid-cols-[3fr_2fr] gap-4 items-start">
          <AIPicks
            onTickerSelect={setSimulatorTicker}
            onSimulate={setSimulatorTicker}
          />
          <SimulatorPanel ticker={simulatorTicker} />
        </div>
      </div>
    </div>
  );
}
