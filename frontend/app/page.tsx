"use client";
import StockChart from "@/components/dashboard/StockChart";
import StockInfoBar from "@/components/dashboard/StockInfoBar";
import { useData } from "@/hooks/useData";
import { api } from "@/lib/api";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState, useCallback } from "react";
import { TrendingUp, Sparkles, Lock } from "lucide-react";

export default function Dashboard() {
  const [selectedTicker, setSelectedTicker] = useState("");
  const router = useRouter();

  const { data: quote } = useData(
    () => selectedTicker ? api.quote(selectedTicker) as Promise<any> : Promise.resolve(null),
    [selectedTicker],
    { refreshInterval: selectedTicker ? 60000 : 0 }
  );

  const handleTickerSelect = useCallback((ticker: string) => {
    setSelectedTicker(ticker);
  }, []);

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
          <div className="ml-auto flex items-center gap-2">
            <Link
              href="/picks"
              className="flex items-center gap-1.5 text-xs text-zinc-400 hover:text-cyan-400 border border-zinc-700 hover:border-cyan-700/50 px-3 py-1.5 rounded-lg transition-colors"
            >
              <Sparkles size={11} />
              AI Picks
            </Link>
            <Link
              href="/simulator"
              className="flex items-center gap-1.5 text-xs text-zinc-400 hover:text-emerald-400 border border-zinc-700 hover:border-emerald-700/50 px-3 py-1.5 rounded-lg transition-colors"
            >
              <TrendingUp size={11} />
              Paper Trader
            </Link>
          </div>
        </div>
      </header>

      {/* Main content */}
      <div className="max-w-[1600px] mx-auto px-3 md:px-4 py-4">
        <div className="grid grid-cols-1 lg:grid-cols-[3fr_2fr] gap-4 items-start">

          {/* Left panel — AI Picks entry card */}
          <div className="space-y-4">
            <Link href="/picks" className="block group">
              <div className="bg-zinc-900 border border-zinc-800 hover:border-cyan-800/50 rounded-xl p-6 transition-colors">
                <div className="flex items-center gap-3 mb-3">
                  <div className="flex items-center justify-center w-9 h-9 rounded-lg bg-cyan-500/10 border border-cyan-500/20">
                    <Sparkles size={16} className="text-cyan-400" />
                  </div>
                  <div>
                    <div className="text-sm font-semibold text-zinc-100 group-hover:text-cyan-400 transition-colors">AI Picks</div>
                    <div className="text-xs text-zinc-500">Long-term picks + bargain buys</div>
                  </div>
                  <div className="ml-auto flex items-center gap-1.5 text-xs text-zinc-600 group-hover:text-zinc-400 transition-colors">
                    <Lock size={11} />
                    <span>Private</span>
                  </div>
                </div>
                <p className="text-xs text-zinc-500 leading-relaxed">
                  AI-generated stock picks across quality compounders and value opportunities.
                  Includes analyst consensus, insider signals, and technical entry zones.
                </p>
                <div className="mt-4 text-xs text-cyan-600 group-hover:text-cyan-400 transition-colors">
                  Enter passcode to view →
                </div>
              </div>
            </Link>
          </div>

          {/* Right panel — Chart */}
          <div className={`lg:sticky lg:top-16 space-y-0 ${selectedTicker ? "block" : "hidden lg:block"}`}>
            <StockChart ticker={selectedTicker} height={500} />
            {quote && <StockInfoBar quote={quote} />}
            {selectedTicker && (
              <div className="mt-2 flex justify-end">
                <Link
                  href={`/simulator?ticker=${encodeURIComponent(selectedTicker)}`}
                  className="flex items-center gap-1.5 text-xs text-zinc-500 hover:text-emerald-400 transition-colors"
                >
                  <TrendingUp size={11} />
                  Trade {selectedTicker} in Paper Trader →
                </Link>
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
