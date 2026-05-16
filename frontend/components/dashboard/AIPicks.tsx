"use client";
import { useState } from "react";
import { useData } from "@/hooks/useData";
import { api } from "@/lib/api";
import { formatPrice, colorClass } from "@/lib/utils";
import { Card } from "@/components/ui/Card";
import { Badge } from "@/components/ui/Badge";
import {
  Sparkles, RefreshCw, TrendingUp, TrendingDown, Minus,
  ShieldAlert, Target, ArrowRight, AlertTriangle, Clock,
  Search, DollarSign, CheckCircle, XCircle, MinusCircle,
  ChevronDown, ChevronUp,
} from "lucide-react";

interface AIPicksProps {
  onTickerSelect: (ticker: string) => void;
  onSimulate?: (ticker: string) => void;
}

const TRADE_TYPE_COLORS: Record<string, string> = {
  // Short-term
  momentum: "bg-cyan-500/15 text-cyan-300 border-cyan-500/30",
  breakout: "bg-emerald-500/15 text-emerald-300 border-emerald-500/30",
  reversal: "bg-purple-500/15 text-purple-300 border-purple-500/30",
  bounce: "bg-yellow-500/15 text-yellow-300 border-yellow-500/30",
  gap_fill: "bg-orange-500/15 text-orange-300 border-orange-500/30",
  // Long-term
  growth: "bg-blue-500/15 text-blue-300 border-blue-500/30",
  value: "bg-indigo-500/15 text-indigo-300 border-indigo-500/30",
  dividend: "bg-teal-500/15 text-teal-300 border-teal-500/30",
  turnaround: "bg-orange-500/15 text-orange-300 border-orange-500/30",
  // Discovery
  disruptor: "bg-amber-500/15 text-amber-300 border-amber-500/30",
  platform: "bg-sky-500/15 text-sky-300 border-sky-500/30",
  "deep-tech": "bg-violet-500/15 text-violet-300 border-violet-500/30",
  speculative: "bg-rose-500/15 text-rose-300 border-rose-500/30",
};

const BIAS_CONFIG = {
  bullish: { icon: <TrendingUp size={14} />, cls: "text-emerald-400", label: "Bullish Bias" },
  bearish: { icon: <TrendingDown size={14} />, cls: "text-red-400", label: "Bearish Bias" },
  neutral: { icon: <Minus size={14} />, cls: "text-yellow-400", label: "Neutral" },
};

const REC_CONFIG: Record<string, { icon: React.ReactNode; cls: string; bg: string; label: string }> = {
  buy:   { icon: <CheckCircle size={14} />, cls: "text-emerald-400", bg: "bg-emerald-500/10 border-emerald-500/30", label: "BUY" },
  hold:  { icon: <MinusCircle size={14} />, cls: "text-yellow-400",  bg: "bg-yellow-500/10 border-yellow-500/30",  label: "HOLD" },
  avoid: { icon: <XCircle size={14} />,    cls: "text-red-400",      bg: "bg-red-500/10 border-red-500/30",        label: "AVOID" },
};

export default function AIPicks({ onTickerSelect, onSimulate }: AIPicksProps) {
  return <AllModePicks onTickerSelect={onTickerSelect} onSimulate={onSimulate} />;
}

// ─── Ticker analysis result card ──────────────────────────────────────────────

function TickerAnalysisCard({
  analysis,
  mode = "short",
  onSelect,
  onSimulate,
}: {
  analysis: any;
  mode?: "short" | "long" | "discovery";
  onSelect: () => void;
  onSimulate?: () => void;
}) {
  const [calcOpen, setCalcOpen] = useState(false);
  const rec = analysis.recommendation?.toLowerCase() as "buy" | "hold" | "avoid";
  const recConf = REC_CONFIG[rec] ?? REC_CONFIG.hold;
  const tradeTypeClass = TRADE_TYPE_COLORS[analysis.trade_type] ?? "bg-zinc-800 text-zinc-400 border-zinc-700";
  const confidenceColor =
    analysis.confidence >= 8 ? "text-emerald-400" :
    analysis.confidence >= 6 ? "text-yellow-400" :
    "text-red-400";

  return (
    <div className={`rounded-xl border overflow-hidden ${calcOpen ? "border-cyan-800/50" : recConf.bg.replace("border-", "border-")}`}
      style={{}}>
      {/* Header */}
      <div className={`flex items-center justify-between px-4 py-3 border-b border-zinc-800/60 ${recConf.bg}`}>
        <div className="flex items-center gap-3">
          <button
            onClick={onSelect}
            className="font-bold text-lg text-zinc-100 hover:text-cyan-400 transition-colors"
          >
            {analysis.ticker}
          </button>
          <span className={`flex items-center gap-1 text-xs font-bold px-2.5 py-1 rounded-lg border ${recConf.bg} ${recConf.cls}`}>
            {recConf.icon} {recConf.label}
          </span>
          {analysis.trade_type && (
            <span className={`text-[11px] font-medium px-2 py-0.5 rounded border ${tradeTypeClass}`}>
              {analysis.trade_type.replace("_", " ")}
            </span>
          )}
        </div>
        <div className="flex items-center gap-2">
          <div className={`text-sm font-bold tabular-nums ${confidenceColor}`}>
            {analysis.confidence}/10
            <span className="text-xs font-normal text-zinc-600 ml-1">confidence</span>
          </div>
          <button
            onClick={() => setCalcOpen((o) => !o)}
            className={`flex items-center gap-1 text-xs border px-2.5 py-1 rounded-lg transition-colors ${
              calcOpen
                ? "bg-cyan-600/20 border-cyan-600/40 text-cyan-400"
                : "bg-zinc-800 border-zinc-700 text-zinc-400 hover:text-cyan-400 hover:border-cyan-800"
            }`}
          >
            $ Returns {calcOpen ? <ChevronUp size={11} /> : <ChevronDown size={11} />}
          </button>
          {onSimulate && (
            <button
              onClick={onSimulate}
              className="flex items-center gap-1 text-xs bg-emerald-600/20 border border-emerald-600/30 text-emerald-400 hover:bg-emerald-600/30 px-2.5 py-1 rounded-lg transition-colors"
            >
              Simulate <ArrowRight size={11} />
            </button>
          )}
        </div>
      </div>

      {/* Price levels */}
      <div className="grid grid-cols-4 gap-0 divide-x divide-zinc-800 bg-zinc-900/60">
        <PriceTile label="Entry Zone" value={`${formatPrice(analysis.entry_low)} – ${formatPrice(analysis.entry_high)}`} className="text-zinc-200" />
        <PriceTile label="Stop Loss" value={formatPrice(analysis.stop_loss)} className="text-red-400" />
        <PriceTile label="Target" value={formatPrice(analysis.target)} className="text-emerald-400" />
        <PriceTile label="Risk/Reward" value={analysis.risk_reward || "—"} className="text-cyan-400" />
      </div>

      {/* Confidence bar */}
      <div className="px-4 py-1.5 bg-zinc-900/40 border-t border-zinc-800/40">
        <div className="h-1 bg-zinc-800 rounded-full overflow-hidden">
          <div
            className={`h-full rounded-full transition-all ${
              analysis.confidence >= 8 ? "bg-emerald-500" :
              analysis.confidence >= 6 ? "bg-yellow-500" : "bg-red-500"
            }`}
            style={{ width: `${(analysis.confidence / 10) * 100}%` }}
          />
        </div>
      </div>

      {/* Thesis — kept exactly as-is */}
      <div className="px-4 py-3 bg-zinc-900/40">
        <p className="text-sm text-zinc-400 leading-relaxed">{analysis.thesis}</p>
        <p className="text-[10px] text-zinc-600 italic mt-2">
          {mode === "discovery"
            ? "Discovery analysis (10+ year horizon) · not financial advice"
            : mode === "long"
              ? "Long-term analysis (6–12 month hold) · not financial advice"
              : analysis.next_trading_day
                ? `For ${analysis.next_trading_day}'s open · not financial advice`
                : "Not financial advice"}
        </p>
      </div>

      {/* Return estimator — same as pick cards */}
      {calcOpen && (
        <InvestmentCalculator pick={analysis} mode={mode} onSimulate={onSimulate} />
      )}
    </div>
  );
}

// ─── Main picks card ──────────────────────────────────────────────────────────

function PickCard({
  pick,
  mode = "short",
  onSelect,
  onSimulate,
  expanded,
  onToggle,
}: {
  pick: any;
  mode?: "short" | "long" | "discovery";
  onSelect: () => void;
  onSimulate?: () => void;
  expanded: boolean;
  onToggle: () => void;
}) {
  const rr = pick.risk_reward || "";
  const tradeTypeClass = TRADE_TYPE_COLORS[pick.trade_type] || "bg-zinc-800 text-zinc-400 border-zinc-700";
  const confidenceColor =
    pick.confidence >= 8 ? "text-emerald-400" :
    pick.confidence >= 6 ? "text-yellow-400" :
    "text-red-400";

  const risk = pick.entry_high && pick.stop_loss ? pick.entry_high - pick.stop_loss : null;
  const reward = pick.entry_low && pick.target ? pick.target - pick.entry_low : null;

  return (
    <div className={`bg-zinc-900 border rounded-xl overflow-hidden transition-colors ${expanded ? "border-cyan-800/50" : "border-zinc-800 hover:border-zinc-700"}`}>
      {/* Header row */}
      <div className="flex items-center justify-between px-4 py-3 border-b border-zinc-800/60">
        <div className="flex items-center gap-3">
          <span className="text-xl font-bold text-cyan-400">#{pick.rank}</span>
          <button
            onClick={onSelect}
            className="font-bold text-lg text-zinc-100 hover:text-cyan-400 transition-colors"
          >
            {pick.ticker}
          </button>
          <span className={`text-[11px] font-medium px-2 py-0.5 rounded border ${tradeTypeClass}`}>
            {pick.trade_type?.replace("_", " ")}
          </span>
        </div>
        <div className="flex items-center gap-2">
          <div className={`text-sm font-bold tabular-nums ${confidenceColor}`}>
            {pick.confidence}/10
            <span className="text-xs font-normal text-zinc-600 ml-1">confidence</span>
          </div>
          <button
            onClick={onToggle}
            className={`flex items-center gap-1 text-xs border px-2.5 py-1 rounded-lg transition-colors ${
              expanded
                ? "bg-cyan-600/20 border-cyan-600/40 text-cyan-400"
                : "bg-zinc-800 border-zinc-700 text-zinc-400 hover:text-cyan-400 hover:border-cyan-800"
            }`}
          >
            $ Returns {expanded ? <ChevronUp size={11} /> : <ChevronDown size={11} />}
          </button>
          {onSimulate && (
            <button
              onClick={onSimulate}
              className="flex items-center gap-1 text-xs bg-emerald-600/20 border border-emerald-600/30 text-emerald-400 hover:bg-emerald-600/30 px-2.5 py-1 rounded-lg transition-colors"
            >
              Simulate <ArrowRight size={11} />
            </button>
          )}
        </div>
      </div>

      {/* Price levels */}
      <div className="grid grid-cols-4 gap-0 divide-x divide-zinc-800">
        <PriceTile label="Entry Zone" value={`${formatPrice(pick.entry_low)} – ${formatPrice(pick.entry_high)}`} className="text-zinc-200" />
        <PriceTile label="Stop Loss" value={formatPrice(pick.stop_loss)} className="text-red-400" />
        <PriceTile label="Target" value={formatPrice(pick.target)} className="text-emerald-400" />
        <PriceTile label="Risk/Reward" value={rr || (risk && reward ? `1:${(reward / risk).toFixed(1)}` : "—")} className="text-cyan-400" />
      </div>

      {/* Confidence bar */}
      <div className="px-4 py-1.5 border-t border-zinc-800/40">
        <div className="h-1 bg-zinc-800 rounded-full overflow-hidden">
          <div
            className={`h-full rounded-full transition-all ${
              pick.confidence >= 8 ? "bg-emerald-500" :
              pick.confidence >= 6 ? "bg-yellow-500" : "bg-red-500"
            }`}
            style={{ width: `${(pick.confidence / 10) * 100}%` }}
          />
        </div>
      </div>

      {/* Thesis */}
      <div className="px-4 py-3">
        <p className="text-sm text-zinc-400 leading-relaxed">{pick.thesis}</p>
      </div>

      {/* Investment calculator — expands inline */}
      {expanded && (
        <InvestmentCalculator pick={pick} mode={mode} onSimulate={onSimulate} />
      )}
    </div>
  );
}

// ─── Investment calculator ────────────────────────────────────────────────────

function holdEstimate(pct: number, mode: "short" | "long" | "discovery" = "short"): string {
  if (mode === "discovery") {
    if (pct < 50)  return "3–5 years";
    if (pct < 100) return "5–10 years";
    return "10+ years";
  }
  if (mode === "long") {
    if (pct < 5)  return "3–6 months";
    if (pct < 15) return "6–12 months";
    if (pct < 30) return "1–2 years";
    return "2+ years";
  }
  if (pct < 1)  return "intraday";
  if (pct < 2)  return "~1 session";
  if (pct < 5)  return "1–3 days";
  if (pct < 10) return "3–7 days";
  if (pct < 20) return "1–2 weeks";
  return "2+ weeks";
}

function InvestmentCalculator({ pick, mode = "short", onSimulate }: { pick: any; mode?: "short" | "long" | "discovery"; onSimulate?: () => void }) {
  const [amount, setAmount] = useState("1000");

  const investment = Math.max(0, parseFloat(amount) || 0);
  const midEntry = pick.entry_low && pick.entry_high ? (pick.entry_low + pick.entry_high) / 2 : 0;
  const shares = midEntry > 0 && investment > 0 ? Math.floor(investment / midEntry) : 0;
  const cost = shares * midEntry;
  const leftover = investment - cost;

  const gainAtTarget  = shares > 0 && pick.target    ? shares * (pick.target - midEntry)    : 0;
  const lossAtStop    = shares > 0 && pick.stop_loss  ? shares * (midEntry - pick.stop_loss) : 0;
  const priceTo5      = shares > 0                    ? midEntry + 5 / shares                : 0;
  const pctTo5        = midEntry > 0 && shares > 0    ? (5 / shares / midEntry) * 100        : 0;
  const pctToTarget   = midEntry > 0 && pick.target   ? ((pick.target - midEntry) / midEntry) * 100 : 0;
  const returnPct     = midEntry > 0 && pick.target   ? ((pick.target - midEntry) / midEntry * 100).toFixed(1) : "—";

  return (
    <div className="px-4 pb-4 pt-3 bg-zinc-950/70 border-t border-cyan-900/30 space-y-3">
      {/* Header + input */}
      <div className="flex items-center gap-3 flex-wrap">
        <span className="text-xs font-semibold text-zinc-300">Return Estimator</span>
        <div className="flex items-center gap-1.5">
          <span className="text-xs text-zinc-500">Invest</span>
          <div className="relative">
            <span className="absolute left-2.5 top-1/2 -translate-y-1/2 text-xs text-zinc-500">$</span>
            <input
              type="number"
              min="0"
              step="100"
              value={amount}
              onChange={(e) => setAmount(e.target.value)}
              className="w-28 pl-5 pr-2 py-1.5 bg-zinc-800 border border-zinc-700 rounded-lg text-sm text-zinc-200 focus:outline-none focus:border-cyan-600 tabular-nums"
            />
          </div>
        </div>
        {shares > 0 && (
          <span className="text-xs text-zinc-600 tabular-nums">
            → {shares} shares @ {formatPrice(midEntry)}
            {leftover > 0.01 && ` · $${leftover.toFixed(2)} left over`}
          </span>
        )}
      </div>

      {shares > 0 ? (
        <>
          {/* Three checkpoints */}
          <div className="grid grid-cols-1 sm:grid-cols-3 gap-2">
            {/* $5 return */}
            <div className="bg-zinc-900 rounded-lg p-3 border border-cyan-900/30">
              <div className="text-[10px] text-zinc-500 uppercase tracking-wider mb-1.5">Hit $5 profit when</div>
              <div className="text-sm font-bold text-cyan-300 tabular-nums">{formatPrice(priceTo5)}</div>
              <div className="text-[10px] text-zinc-500 mt-1">
                +{pctTo5.toFixed(2)}% move · est. <span className="text-zinc-400">{holdEstimate(pctTo5, mode)}</span>
              </div>
            </div>

            {/* Full target */}
            <div className="bg-zinc-900 rounded-lg p-3 border border-emerald-900/40">
              <div className="text-[10px] text-zinc-500 uppercase tracking-wider mb-1.5">At full target ({formatPrice(pick.target)})</div>
              <div className={`text-sm font-bold tabular-nums ${gainAtTarget >= 0 ? "text-emerald-400" : "text-red-400"}`}>
                {gainAtTarget >= 0 ? "+" : "−"}${Math.abs(gainAtTarget).toFixed(2)}
                <span className="text-xs font-normal text-zinc-600 ml-1">({returnPct}%)</span>
              </div>
              <div className="text-[10px] text-zinc-500 mt-1">
                +{pctToTarget.toFixed(1)}% move · est. <span className="text-zinc-400">{holdEstimate(pctToTarget, mode)}</span>
              </div>
            </div>

            {/* Stop loss */}
            <div className="bg-zinc-900 rounded-lg p-3 border border-red-900/30">
              <div className="text-[10px] text-zinc-500 uppercase tracking-wider mb-1.5">Stop loss risk ({formatPrice(pick.stop_loss)})</div>
              <div className="text-sm font-bold text-red-400 tabular-nums">−${lossAtStop.toFixed(2)}</div>
              <div className="text-[10px] text-zinc-500 mt-1">
                max loss if stop is hit
              </div>
            </div>
          </div>

          {/* Minimum to make $5 hint */}
          {pctToTarget > 0 && (
            <p className="text-[10px] text-zinc-600">
              Min to make $5 at target: <span className="text-zinc-400 tabular-nums">${(5 / (pctToTarget / 100)).toFixed(2)}</span>
              {mode === "discovery"
                ? " · These are multi-year holds. Short-term volatility is expected — conviction in the 10-year thesis matters more than price action."
                : mode === "long"
                  ? " · Hold estimates are based on the target % move — actual timing depends on fundamentals and macro catalysts."
                  : " · Hold estimates are rough — momentum plays often resolve faster than swing setups."}
            </p>
          )}

          {/* Open in Simulator */}
          {onSimulate && (
            <button
              onClick={onSimulate}
              className="flex items-center gap-1.5 text-xs bg-emerald-600/20 border border-emerald-600/30 text-emerald-400 hover:bg-emerald-600/30 px-3 py-1.5 rounded-lg transition-colors"
            >
              Open in Simulator <ArrowRight size={11} />
            </button>
          )}
        </>
      ) : (
        <p className="text-xs text-zinc-600">Enter an amount above to see return projections.</p>
      )}
    </div>
  );
}

// ─── All mode — three panels, single fetch ───────────────────────────────────

const ALL_MODE_CONFIGS = [
  { mode: "short"     as const, label: "Day Trading",  accentCls: "text-cyan-400",   badgeCls: "border-cyan-800/40 text-cyan-400",    desc: "Short-term picks for tomorrow's open" },
  { mode: "long"      as const, label: "Long-Term",    accentCls: "text-purple-400", badgeCls: "border-purple-800/40 text-purple-400", desc: "6–12 month conviction plays" },
  { mode: "discovery" as const, label: "Discovery",    accentCls: "text-amber-400",  badgeCls: "border-amber-800/40 text-amber-400",   desc: "10-year disruptors" },
];

function renderError(error: string) {
  const isNoCredits = error.includes("coin jar") || error.includes("credits") || error.includes("billing");
  return (
    <div className="px-4 py-3">
      {isNoCredits ? (
        <div className="rounded-lg border border-amber-700/40 bg-amber-950/20 px-3 py-2 space-y-1">
          <p className="text-xs text-amber-300 font-semibold">🪙 Out of AI Credits</p>
          <p className="text-xs text-amber-200/70">{error}</p>
          <a href="https://console.anthropic.com/settings/billing" target="_blank" rel="noopener noreferrer"
            className="text-xs text-amber-400 underline underline-offset-2 hover:text-amber-300">
            console.anthropic.com/settings/billing ↗
          </a>
        </div>
      ) : (
        <div className="flex items-start gap-2 text-xs text-red-400 bg-red-500/10 rounded-lg px-3 py-2">
          <AlertTriangle size={12} className="shrink-0 mt-0.5" />
          {error.includes("ANTHROPIC_API_KEY") || error.includes("503")
            ? "Add ANTHROPIC_API_KEY to enable AI picks."
            : `Error: ${error}`}
        </div>
      )}
    </div>
  );
}

function AllModePicks({ onTickerSelect, onSimulate }: { onTickerSelect: (t: string) => void; onSimulate?: (t: string) => void }) {
  const [fetchKey, setFetchKey] = useState(0);
  const [tickerInput, setTickerInput] = useState("");
  const [tickerAnalysis, setTickerAnalysis] = useState<any>(null);
  const [tickerLoading, setTickerLoading] = useState(false);
  const [tickerError, setTickerError] = useState<string | null>(null);
  const [expandedPick, setExpandedPick] = useState<string | null>(null);
  // Per-panel "show more" — track how many to show per mode
  const [showMore, setShowMore] = useState<Record<string, number>>({ short: 5, long: 5, discovery: 5 });

  // Single fetch for all 3 modes — sequential on backend, no burst
  const { data: allData, loading, error, refetch } = useData(
    () => api.aiPicksAll() as Promise<any>,
    [fetchKey],
    { refreshInterval: 0 }
  );

  const handleAnalyzeTicker = async () => {
    const t = tickerInput.trim().toUpperCase();
    if (!t) return;
    setTickerLoading(true);
    setTickerError(null);
    setTickerAnalysis(null);
    try {
      // Single combined Claude call — all 3 horizons at once
      const result = await api.analyzeTickerAll(t) as any;
      if (result?.error) throw new Error(result.error);
      setTickerAnalysis(result);
      // Load the ticker in the simulator too
      onTickerSelect(t);
    } catch (e) {
      setTickerError(e instanceof Error ? e.message : "Analysis failed");
    } finally {
      setTickerLoading(false);
    }
  };

  const handleRefresh = () => {
    setFetchKey((k) => k + 1);
    refetch();
  };

  return (
    <div className="space-y-4">
      {/* Ticker Analyzer */}
      <div className="bg-zinc-900 border border-zinc-800 rounded-xl p-4">
        <div className="flex items-center gap-2 mb-3">
          <Search size={14} className="text-zinc-400" />
          <span className="text-sm font-semibold text-zinc-200">Analyze Any Stock</span>
          <span className="text-xs text-zinc-600 border border-zinc-700 rounded px-1.5 py-0.5">AI · All 3 Horizons</span>
        </div>
        <div className="flex gap-2">
          <input
            type="text"
            placeholder="Ticker symbol — get Short, Long & Discovery analysis at once"
            value={tickerInput}
            onChange={(e) => setTickerInput(e.target.value.toUpperCase())}
            onKeyDown={(e) => e.key === "Enter" && handleAnalyzeTicker()}
            maxLength={10}
            className="flex-1 bg-zinc-800 border border-zinc-700 rounded-lg px-3 py-2 text-sm text-zinc-200 placeholder-zinc-600 focus:outline-none focus:border-cyan-500 transition-colors"
          />
          <button
            onClick={handleAnalyzeTicker}
            disabled={tickerLoading || !tickerInput.trim()}
            className="px-4 py-2 bg-cyan-600/20 border border-cyan-600/30 text-cyan-400 text-sm rounded-lg hover:bg-cyan-600/30 transition-colors disabled:opacity-40 whitespace-nowrap"
          >
            {tickerLoading ? "Analyzing…" : "Analyze All"}
          </button>
        </div>
        {tickerError && (
          <p className="text-xs text-red-400 mt-2 flex items-center gap-1">
            <AlertTriangle size={11} /> {tickerError}
          </p>
        )}
        {tickerLoading && (
          <div className="mt-3 space-y-1.5 animate-pulse">
            <div className="h-3 bg-zinc-800 rounded w-3/4" />
            <div className="h-3 bg-zinc-800 rounded w-1/2" />
          </div>
        )}
        {tickerAnalysis && !tickerLoading && (
          <div className="mt-3 space-y-3">
            {ALL_MODE_CONFIGS.map((cfg) => {
              const a = tickerAnalysis[cfg.mode];
              if (!a) return null;
              return (
                <div key={cfg.mode}>
                  <div className={`text-[10px] font-semibold uppercase tracking-wider mb-1 ${cfg.accentCls}`}>
                    {cfg.label} Analysis
                  </div>
                  <TickerAnalysisCard
                    analysis={a}
                    mode={cfg.mode}
                    onSelect={() => onTickerSelect(a.ticker)}
                    onSimulate={onSimulate ? () => onSimulate(a.ticker) : undefined}
                  />
                </div>
              );
            })}
          </div>
        )}
      </div>

      {/* Header */}
      <div className="flex items-center justify-between px-1">
        <div className="flex items-center gap-2">
          <Sparkles size={14} className="text-zinc-400" />
          <span className="text-sm font-semibold text-zinc-200">AI Picks — 3 Timeframes</span>
          {allData && !loading && (
            <span className="text-[10px] text-zinc-600 border border-zinc-700 rounded px-1.5 py-0.5">
              {allData.short?.generated_at ?? ""}
            </span>
          )}
        </div>
        <button
          onClick={handleRefresh}
          disabled={loading}
          className="flex items-center gap-1.5 text-xs text-zinc-400 hover:text-cyan-400 transition-colors disabled:opacity-40"
        >
          <RefreshCw size={12} className={loading ? "animate-spin" : ""} />
          {loading ? "Loading…" : "Refresh"}
        </button>
      </div>

      {/* Top-level error (entire picks-all failed) */}
      {error && renderError(error)}

      {/* Three mode panels */}
      {ALL_MODE_CONFIGS.map((cfg) => {
        const modeData = allData?.[cfg.mode];
        const modeLoading = loading;
        const picks: any[] = modeData?.picks ?? [];
        const visibleCount = showMore[cfg.mode] ?? 5;
        const visiblePicks = picks.slice(0, visibleCount);
        const hasMore = picks.length > visibleCount;

        return (
          <div key={cfg.mode} className="bg-zinc-900 border border-zinc-800 rounded-xl overflow-hidden">
            {/* Panel header */}
            <div className="flex items-center justify-between px-4 py-3 border-b border-zinc-800">
              <div className="flex items-center gap-2 min-w-0">
                <span className={`font-semibold text-sm shrink-0 ${cfg.accentCls}`}>{cfg.label}</span>
                <span className={`text-[10px] border rounded px-1.5 py-0.5 shrink-0 ${cfg.badgeCls}`}>{cfg.desc}</span>
              </div>
              {modeData?.bias && (
                <span className={`text-xs shrink-0 ${
                  modeData.bias === "bullish" ? "text-emerald-400" :
                  modeData.bias === "bearish" ? "text-red-400" : "text-yellow-400"
                }`}>{modeData.bias}</span>
              )}
            </div>

            {modeLoading && (
              <div className="px-4 py-3 space-y-2 animate-pulse">
                {[...Array(3)].map((_, i) => (
                  <div key={i} className="h-8 bg-zinc-800 rounded" />
                ))}
              </div>
            )}

            {modeData && !modeLoading && (
              <div className="px-4 py-3 space-y-3">
                {modeData.market_summary && (
                  <p className="text-xs text-zinc-400 leading-relaxed">{modeData.market_summary}</p>
                )}

                {picks.length === 0 && (
                  <p className="text-xs text-zinc-600 italic">No picks available — screener may be loading or rate-limited. Try refreshing.</p>
                )}

                {/* Picks list — 5 visible, expandable detail */}
                {picks.length > 0 && (
                  <div className="space-y-1.5">
                    {visiblePicks.map((pick: any) => {
                      const key = `${cfg.mode}-${pick.ticker}`;
                      const isExpanded = expandedPick === key;
                      return (
                        <div key={key} className="rounded-xl border border-zinc-800 overflow-hidden">
                          {/* Compact row */}
                          <div className="flex items-center justify-between bg-zinc-800/60 px-3 py-2 gap-2">
                            <div className="flex items-center gap-2 min-w-0">
                              <span className="text-xs text-zinc-600 shrink-0">#{pick.rank}</span>
                              <button
                                onClick={() => onTickerSelect(pick.ticker)}
                                className={`font-bold text-sm shrink-0 ${cfg.accentCls} hover:underline`}
                              >
                                {pick.ticker}
                              </button>
                              <span className={`text-[10px] font-medium px-1.5 py-0.5 rounded border shrink-0 ${TRADE_TYPE_COLORS[pick.trade_type] ?? "bg-zinc-800 text-zinc-400 border-zinc-700"}`}>
                                {pick.trade_type?.replace("_", " ")}
                              </span>
                              <span className="text-xs text-zinc-500 truncate hidden md:block">{pick.thesis?.slice(0, 70)}…</span>
                            </div>
                            <div className="flex items-center gap-2 shrink-0">
                              <span className={`text-xs font-bold tabular-nums ${
                                pick.confidence >= 8 ? "text-emerald-400" :
                                pick.confidence >= 6 ? "text-yellow-400" : "text-red-400"
                              }`}>{pick.confidence}/10</span>
                              {onSimulate && (
                                <button
                                  onClick={() => onSimulate(pick.ticker)}
                                  className="text-[10px] bg-emerald-600/20 border border-emerald-600/30 text-emerald-400 hover:bg-emerald-600/30 px-2 py-0.5 rounded transition-colors"
                                >
                                  Sim
                                </button>
                              )}
                              <button
                                onClick={() => setExpandedPick(isExpanded ? null : key)}
                                className="flex items-center gap-0.5 text-[10px] text-zinc-500 hover:text-zinc-300 px-1.5 py-0.5 rounded transition-colors"
                              >
                                Detail {isExpanded ? <ChevronUp size={10} /> : <ChevronDown size={10} />}
                              </button>
                            </div>
                          </div>
                          {/* Expanded detail */}
                          {isExpanded && (
                            <PickCard
                              pick={pick}
                              mode={cfg.mode}
                              onSelect={() => onTickerSelect(pick.ticker)}
                              onSimulate={onSimulate ? () => onSimulate(pick.ticker) : undefined}
                              expanded={false}
                              onToggle={() => {}}
                            />
                          )}
                        </div>
                      );
                    })}

                    {/* Load more / show less */}
                    {hasMore && (
                      <button
                        onClick={() => setShowMore((s) => ({ ...s, [cfg.mode]: visibleCount + 5 }))}
                        className="w-full text-xs text-zinc-500 hover:text-zinc-300 py-1.5 border border-zinc-800 rounded-lg transition-colors"
                      >
                        Show {Math.min(5, picks.length - visibleCount)} more picks ↓
                      </button>
                    )}
                    {visibleCount > 5 && (
                      <button
                        onClick={() => setShowMore((s) => ({ ...s, [cfg.mode]: 5 }))}
                        className="w-full text-xs text-zinc-600 hover:text-zinc-400 py-1 transition-colors"
                      >
                        Show less ↑
                      </button>
                    )}
                  </div>
                )}

                {/* Avoid */}
                {modeData.avoid?.length > 0 && (
                  <div className="flex items-center gap-2 flex-wrap pt-1">
                    <span className="text-[10px] text-red-500 font-semibold uppercase">Avoid:</span>
                    {modeData.avoid.map((t: string) => (
                      <span key={t} className="text-[10px] font-bold bg-red-500/10 border border-red-500/20 text-red-400 px-1.5 py-0.5 rounded">
                        {t}
                      </span>
                    ))}
                    {modeData.avoid_reason && (
                      <span className="text-[10px] text-zinc-600 italic">{modeData.avoid_reason}</span>
                    )}
                  </div>
                )}
              </div>
            )}
          </div>
        );
      })}
      <p className="text-[10px] text-zinc-700 italic px-1">
        AI-generated for simulation purposes only. Not financial advice. Always verify independently.
      </p>
    </div>
  );
}

// ─── Price tile ───────────────────────────────────────────────────────────────

function PriceTile({ label, value, className }: { label: string; value: string; className?: string }) {
  return (
    <div className="px-3 py-2.5 text-center">
      <div className="text-[10px] text-zinc-600 mb-0.5 uppercase tracking-wider">{label}</div>
      <div className={`text-xs font-semibold tabular-nums ${className}`}>{value}</div>
    </div>
  );
}
