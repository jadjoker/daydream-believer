"use client";
import AIPicks from "@/components/dashboard/AIPicks";
import StockChart from "@/components/dashboard/StockChart";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState } from "react";
import { TrendingUp } from "lucide-react";

export default function Dashboard() {
  const [selectedTicker, setSelectedTicker] = useState("");
  const router = useRouter();

  const handleSimulate = (ticker: string) => {
    router.push(`/simulator?ticker=${encodeURIComponent(ticker)}`);
  };

  const handleTickerSelect = (ticker: string) => {
    setSelectedTicker(ticker);
  };

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
          <div className="ml-auto">
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
          <AIPicks
            onTickerSelect={handleTickerSelect}
            onSimulate={handleSimulate}
          />

          {/* Sticky chart panel */}
          <div className="lg:sticky lg:top-16">
            <StockChart
              ticker={selectedTicker}
              height={580}
            />
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
