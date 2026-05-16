"use client";
import { useState } from "react";
import MarketOverview from "@/components/dashboard/MarketOverview";
import StockSearch from "@/components/dashboard/StockSearch";
import StockChart from "@/components/dashboard/StockChart";
import TechnicalSignals from "@/components/dashboard/TechnicalSignals";
import SentimentPanel from "@/components/dashboard/SentimentPanel";
import OptionsFlow from "@/components/dashboard/OptionsFlow";
import NewsPanel from "@/components/dashboard/NewsPanel";
import StockScreener from "@/components/dashboard/StockScreener";
import InsiderTrades from "@/components/dashboard/InsiderTrades";
import EarningsCalendar from "@/components/dashboard/EarningsCalendar";
import Watchlist from "@/components/dashboard/Watchlist";
import StockQuotePanel from "@/components/dashboard/StockQuotePanel";
import SimulatorPanel from "@/components/dashboard/SimulatorPanel";
import AIPicks from "@/components/dashboard/AIPicks";
import { useData } from "@/hooks/useData";
import { api } from "@/lib/api";
import { LayoutList, Newspaper, X, ChevronDown, ChevronUp, FlaskConical, TrendingUp, Clock, Rocket } from "lucide-react";
import FundamentalsPanel from "@/components/dashboard/FundamentalsPanel";

type Mode = "short" | "long" | "discovery";
type ResearchTab = "overview" | "technicals" | "sentiment" | "options" | "news" | "insider" | "screener" | "fundamentals";

const SHORT_RESEARCH_TABS: { id: ResearchTab; label: string }[] = [
  { id: "overview", label: "Overview" },
  { id: "technicals", label: "Technicals" },
  { id: "sentiment", label: "Sentiment" },
  { id: "options", label: "Options Flow" },
  { id: "news", label: "News" },
  { id: "insider", label: "Insider / SEC" },
  { id: "screener", label: "Screener" },
];

const LONG_RESEARCH_TABS: { id: ResearchTab; label: string }[] = [
  { id: "fundamentals", label: "Fundamentals" },
  { id: "overview", label: "Overview" },
  { id: "news", label: "News" },
  { id: "insider", label: "Insider / SEC" },
  { id: "technicals", label: "Technicals" },
  { id: "screener", label: "Screener" },
];

const DISCOVERY_RESEARCH_TABS: { id: ResearchTab; label: string }[] = [
  { id: "fundamentals", label: "Growth Metrics" },
  { id: "news", label: "News" },
  { id: "insider", label: "Insider / SEC" },
  { id: "overview", label: "Overview" },
];

function MobileDrawer({ open, onClose, children }: { open: boolean; onClose: () => void; children: React.ReactNode }) {
  if (!open) return null;
  return (
    <div className="fixed inset-0 z-40 flex lg:hidden">
      <div className="absolute inset-0 bg-black/60 backdrop-blur-sm" onClick={onClose} />
      <div className="relative z-50 w-80 max-w-[90vw] bg-zinc-950 border-r border-zinc-800 h-full overflow-y-auto p-4 space-y-4">
        <button onClick={onClose} className="absolute top-3 right-3 text-zinc-500 hover:text-zinc-200">
          <X size={18} />
        </button>
        {children}
      </div>
    </div>
  );
}

function RightDrawer({ open, onClose, children }: { open: boolean; onClose: () => void; children: React.ReactNode }) {
  if (!open) return null;
  return (
    <div className="fixed inset-0 z-40 flex justify-end lg:hidden">
      <div className="absolute inset-0 bg-black/60 backdrop-blur-sm" onClick={onClose} />
      <div className="relative z-50 w-80 max-w-[90vw] bg-zinc-950 border-l border-zinc-800 h-full overflow-y-auto p-4 space-y-4">
        <button onClick={onClose} className="absolute top-3 left-3 text-zinc-500 hover:text-zinc-200">
          <X size={18} />
        </button>
        <div className="pt-6">{children}</div>
      </div>
    </div>
  );
}

export default function Dashboard() {
  const [ticker, setTicker] = useState("AAPL");
  const [mode, setMode] = useState<Mode>("short");
  const [researchOpen, setResearchOpen] = useState(false);
  const [activeResearchTab, setActiveResearchTab] = useState<ResearchTab>("overview");

  const researchTabs = mode === "discovery" ? DISCOVERY_RESEARCH_TABS : mode === "long" ? LONG_RESEARCH_TABS : SHORT_RESEARCH_TABS;

  const handleModeSwitch = (m: Mode) => {
    setMode(m);
    setActiveResearchTab(m === "short" ? "overview" : "fundamentals");
  };
  const [leftOpen, setLeftOpen] = useState(false);
  const [rightOpen, setRightOpen] = useState(false);

  const { data: quote } = useData(
    () => api.quote(ticker) as Promise<any>,
    [ticker],
    { refreshInterval: 30000 }
  );

  const handleTickerSelect = (t: string) => {
    setTicker(t);
    setLeftOpen(false);
  };

  const handleSimulate = (t: string) => {
    setTicker(t);
  };

  return (
    <div className="min-h-screen bg-zinc-950">
      {/* Header */}
      <header className="border-b border-zinc-800 bg-zinc-950/90 backdrop-blur-sm sticky top-0 z-20">
        <div className="max-w-[1600px] mx-auto px-3 py-3 flex items-center gap-2 md:gap-4">
          <button
            className="lg:hidden shrink-0 p-1.5 text-zinc-400 hover:text-cyan-400 transition-colors"
            onClick={() => setLeftOpen(true)}
            title="Watchlist"
          >
            <LayoutList size={18} />
          </button>

          <div className="flex items-center gap-2 shrink-0">
            <span className="text-lg font-bold text-cyan-400">daydream</span>
            <span className="text-lg font-light text-zinc-400 hidden sm:inline">believer</span>
          </div>

          <div className="flex-1 min-w-0">
            <StockSearch onSelect={handleTickerSelect} currentTicker={ticker} />
          </div>

          {/* Mode toggle */}
          <div className="flex rounded-lg overflow-hidden border border-zinc-700 shrink-0">
            <button
              onClick={() => handleModeSwitch("short")}
              className={`flex items-center gap-1 px-2.5 py-1.5 text-xs font-semibold transition-colors ${
                mode === "short" ? "bg-cyan-600 text-white" : "bg-zinc-800 text-zinc-500 hover:text-zinc-300"
              }`}
              title="Day trading mode"
            >
              <Clock size={11} /> Short
            </button>
            <button
              onClick={() => handleModeSwitch("long")}
              className={`flex items-center gap-1 px-2.5 py-1.5 text-xs font-semibold transition-colors ${
                mode === "long" ? "bg-purple-600 text-white" : "bg-zinc-800 text-zinc-500 hover:text-zinc-300"
              }`}
              title="Long-term investing mode (6–12 months)"
            >
              <TrendingUp size={11} /> Long
            </button>
            <button
              onClick={() => handleModeSwitch("discovery")}
              className={`flex items-center gap-1 px-2.5 py-1.5 text-xs font-semibold transition-colors ${
                mode === "discovery" ? "bg-amber-600 text-white" : "bg-zinc-800 text-zinc-500 hover:text-zinc-300"
              }`}
              title="Discovery mode — next 10-year disruptors"
            >
              <Rocket size={11} /> Discovery
            </button>
          </div>

          <div className="text-xs text-zinc-600 shrink-0 hidden md:block">
            For reference only. Not financial advice.
          </div>

          <button
            className="lg:hidden shrink-0 p-1.5 text-zinc-400 hover:text-cyan-400 transition-colors"
            onClick={() => setRightOpen(true)}
            title="News"
          >
            <Newspaper size={18} />
          </button>
        </div>
      </header>

      {/* Mobile drawers */}
      <MobileDrawer open={leftOpen} onClose={() => setLeftOpen(false)}>
        <Watchlist onTickerSelect={handleTickerSelect} selectedTicker={ticker} />
        <EarningsCalendar />
      </MobileDrawer>

      <RightDrawer open={rightOpen} onClose={() => setRightOpen(false)}>
        <NewsPanel />
      </RightDrawer>

      <div className="max-w-[1600px] mx-auto px-3 md:px-4 py-4 space-y-4">
        {/* Market Overview strip */}
        <div className="overflow-x-auto">
          <MarketOverview onTickerSelect={handleTickerSelect} />
        </div>

        {/* ── Hero: AI Picks + Simulator ── */}
        <div className="grid grid-cols-1 lg:grid-cols-[3fr_2fr] gap-4 items-start">
          {/* AI Picks — primary left panel */}
          <AIPicks onTickerSelect={handleTickerSelect} onSimulate={handleSimulate} mode={mode} />

          {/* Simulator — primary right panel */}
          <SimulatorPanel ticker={ticker} />
        </div>

        {/* ── Research Tools (collapsed by default) ── */}
        <div className="border border-zinc-800 rounded-xl overflow-hidden">
          <button
            onClick={() => setResearchOpen((o) => !o)}
            className="w-full flex items-center justify-between px-4 py-3 bg-zinc-900/80 hover:bg-zinc-800/60 transition-colors text-left group"
          >
            <div className="flex items-center gap-2">
              <FlaskConical size={14} className="text-zinc-500 group-hover:text-zinc-400 transition-colors" />
              <span className="text-sm font-medium text-zinc-400 group-hover:text-zinc-300 transition-colors">
                Research Tools
              </span>
              <span className="text-xs text-zinc-600 border border-zinc-700 rounded px-1.5 py-0.5 font-mono">
                {ticker}
              </span>
              {mode === "long" && (
                <span className="text-[10px] text-purple-400 border border-purple-800/40 rounded px-1.5 py-0.5">
                  Long-Term View
                </span>
              )}
              {mode === "discovery" && (
                <span className="text-[10px] text-amber-400 border border-amber-800/40 rounded px-1.5 py-0.5">
                  Discovery View
                </span>
              )}
            </div>
            {researchOpen
              ? <ChevronUp size={14} className="text-zinc-600" />
              : <ChevronDown size={14} className="text-zinc-600" />}
          </button>

          {researchOpen && (
            <div className="bg-zinc-950 border-t border-zinc-800 p-4">
              <div className="flex gap-4">
                {/* Left sidebar */}
                <div className="hidden lg:block w-56 shrink-0 space-y-4">
                  <Watchlist onTickerSelect={handleTickerSelect} selectedTicker={ticker} />
                  <EarningsCalendar />
                </div>

                {/* Center: chart + tabs */}
                <div className="flex-1 min-w-0 space-y-4">
                  <StockChart ticker={ticker} price={quote?.price} changePct={quote?.change_pct} />

                  {/* Research tab nav */}
                  <div className="overflow-x-auto scrollbar-none">
                    <div className="flex gap-1 border-b border-zinc-800 min-w-max">
                      {researchTabs.map((tab) => (
                        <button
                          key={tab.id}
                          onClick={() => setActiveResearchTab(tab.id)}
                          className={`px-3 md:px-4 py-2 text-xs md:text-sm font-medium rounded-t-lg transition-colors border-b-2 whitespace-nowrap ${
                            activeResearchTab === tab.id
                              ? mode === "discovery"
                                ? "border-amber-500 text-amber-400 bg-amber-500/5"
                                : mode === "long"
                                  ? "border-purple-500 text-purple-400 bg-purple-500/5"
                                  : "border-cyan-500 text-cyan-400 bg-cyan-500/5"
                              : "border-transparent text-zinc-500 hover:text-zinc-300 hover:border-zinc-700"
                          }`}
                        >
                          {tab.label}
                        </button>
                      ))}
                    </div>
                  </div>

                  {/* Research tab content */}
                  <div>
                    {activeResearchTab === "fundamentals" && <FundamentalsPanel ticker={ticker} />}
                    {activeResearchTab === "overview" && (
                      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                        <StockQuotePanel ticker={ticker} />
                        <SentimentPanel ticker={ticker} />
                      </div>
                    )}
                    {activeResearchTab === "technicals" && <TechnicalSignals ticker={ticker} />}
                    {activeResearchTab === "sentiment" && <SentimentPanel ticker={ticker} />}
                    {activeResearchTab === "options" && <OptionsFlow ticker={ticker} />}
                    {activeResearchTab === "news" && <NewsPanel ticker={ticker} />}
                    {activeResearchTab === "insider" && <InsiderTrades ticker={ticker} />}
                    {activeResearchTab === "screener" && (
                      <StockScreener onTickerSelect={handleTickerSelect} />
                    )}
                  </div>
                </div>

                {/* Right sidebar: news */}
                <div className="hidden lg:block w-72 shrink-0">
                  <NewsPanel />
                </div>
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
