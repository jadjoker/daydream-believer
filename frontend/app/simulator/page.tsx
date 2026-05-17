"use client";
import { Suspense, useState } from "react";
import { useSearchParams } from "next/navigation";
import SimulatorPanel from "@/components/dashboard/SimulatorPanel";
import Link from "next/link";
import { ArrowLeft, TrendingUp } from "lucide-react";

function SimulatorContent() {
  const searchParams = useSearchParams();
  const initialTicker = searchParams.get("ticker") ?? "";
  const [ticker, setTicker] = useState(initialTicker);

  return (
    <SimulatorPanel ticker={ticker} onTickerChange={setTicker} />
  );
}

export default function SimulatorPage() {
  return (
    <div className="min-h-screen bg-zinc-950">
      <header className="border-b border-zinc-800 bg-zinc-950/90 backdrop-blur-sm sticky top-0 z-20">
        <div className="max-w-[1400px] mx-auto px-3 py-2.5 flex items-center gap-3">
          <Link
            href="/"
            className="flex items-center gap-1.5 text-xs text-zinc-500 hover:text-cyan-400 transition-colors mr-1"
          >
            <ArrowLeft size={12} /> Back
          </Link>
          <span className="text-base font-bold text-cyan-400">daydream</span>
          <span className="text-base font-light text-zinc-400 hidden sm:inline">believer</span>
          <span className="text-xs text-zinc-600 border-l border-zinc-800 pl-3 ml-0.5 hidden sm:inline flex items-center gap-1">
            <TrendingUp size={10} className="inline mr-1" />
            Paper Trader
          </span>
          <div className="ml-auto text-xs text-zinc-700 hidden lg:block">
            For simulation only. Not real money.
          </div>
        </div>
      </header>

      <div className="max-w-[1400px] mx-auto px-3 md:px-4 py-4">
        <Suspense fallback={
          <div className="flex items-center justify-center py-20 text-zinc-500 text-sm">
            Loading simulator…
          </div>
        }>
          <SimulatorContent />
        </Suspense>
      </div>
    </div>
  );
}
