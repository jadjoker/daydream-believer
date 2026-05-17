"use client";
import { useState, useEffect, useRef } from "react";
import { useData } from "@/hooks/useData";
import { api } from "@/lib/api";
import { formatPrice } from "@/lib/utils";
import {
  Sparkles, RefreshCw,
  ShieldAlert, Target, ArrowRight, AlertTriangle,
  Search, CheckCircle, XCircle, MinusCircle,
  ChevronDown, ChevronUp, ChevronLeft, ChevronRight,
  Tag,
} from "lucide-react";

interface AIPicksProps {
  onTickerSelect: (ticker: string) => void;
  onSimulate?: (ticker: string) => void;
}

type HorizonFilter = "all" | "1-3yr" | "3-5yr" | "5-10yr";

const HORIZON_LABELS: Record<string, string> = {
  "1-3yr":  "1–3 yr",
  "3-5yr":  "3–5 yr",
  "5-10yr": "5–10 yr",
};

const HORIZON_COLORS: Record<string, string> = {
  "1-3yr":  "bg-sky-500/15 text-sky-300 border-sky-500/30",
  "3-5yr":  "bg-violet-500/15 text-violet-300 border-violet-500/30",
  "5-10yr": "bg-amber-500/15 text-amber-300 border-amber-500/30",
};

const TRADE_TYPE_COLORS: Record<string, string> = {
  growth:     "bg-blue-500/15 text-blue-300 border-blue-500/30",
  value:      "bg-indigo-500/15 text-indigo-300 border-indigo-500/30",
  dividend:   "bg-teal-500/15 text-teal-300 border-teal-500/30",
  turnaround: "bg-orange-500/15 text-orange-300 border-orange-500/30",
  compounder: "bg-emerald-500/15 text-emerald-300 border-emerald-500/30",
  disruptor:  "bg-amber-500/15 text-amber-300 border-amber-500/30",
  platform:   "bg-sky-500/15 text-sky-300 border-sky-500/30",
  "deep-tech":"bg-violet-500/15 text-violet-300 border-violet-500/30",
  speculative:"bg-rose-500/15 text-rose-300 border-rose-500/30",
  momentum:   "bg-cyan-500/15 text-cyan-300 border-cyan-500/30",
};

const REC_CONFIG: Record<string, { icon: React.ReactNode; cls: string; bg: string; label: string }> = {
  buy:   { icon: <CheckCircle size={14} />, cls: "text-emerald-400", bg: "bg-emerald-500/10 border-emerald-500/30", label: "BUY" },
  hold:  { icon: <MinusCircle size={14} />, cls: "text-yellow-400",  bg: "bg-yellow-500/10 border-yellow-500/30",  label: "HOLD" },
  avoid: { icon: <XCircle size={14} />,    cls: "text-red-400",      bg: "bg-red-500/10 border-red-500/30",        label: "AVOID" },
};

export default function AIPicks({ onTickerSelect, onSimulate }: AIPicksProps) {
  return <AllPicks onTickerSelect={onTickerSelect} onSimulate={onSimulate} />;
}

// ─── Horizon badge ────────────────────────────────────────────────────────────

function HorizonBadge({ horizon }: { horizon?: string }) {
  if (!horizon) return null;
  return (
    <span className={`text-[10px] font-semibold px-2 py-0.5 rounded border ${HORIZON_COLORS[horizon] ?? "bg-zinc-800 text-zinc-400 border-zinc-700"}`}>
      {HORIZON_LABELS[horizon] ?? horizon}
    </span>
  );
}

// ─── Horizon filter bar ───────────────────────────────────────────────────────

function HorizonFilterBar({
  value,
  counts,
  onChange,
}: {
  value: HorizonFilter;
  counts: Record<HorizonFilter, number>;
  onChange: (v: HorizonFilter) => void;
}) {
  const options: { key: HorizonFilter; label: string }[] = [
    { key: "all",    label: "All" },
    { key: "1-3yr",  label: "1–3 yr" },
    { key: "3-5yr",  label: "3–5 yr" },
    { key: "5-10yr", label: "5–10 yr" },
  ];
  return (
    <div className="flex items-center gap-1 flex-wrap">
      {options.map((o) => {
        const active = value === o.key;
        const cnt = counts[o.key];
        return (
          <button
            key={o.key}
            onClick={() => onChange(o.key)}
            className={`flex items-center gap-1 text-[11px] px-2.5 py-1 rounded-lg border transition-colors ${
              active
                ? "bg-cyan-600/20 border-cyan-600/40 text-cyan-300 font-semibold"
                : "bg-zinc-800 border-zinc-700 text-zinc-400 hover:text-zinc-300 hover:border-zinc-600"
            }`}
          >
            {o.label}
            {cnt > 0 && (
              <span className={`text-[10px] ${active ? "text-cyan-500" : "text-zinc-600"}`}>{cnt}</span>
            )}
          </button>
        );
      })}
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

// ─── Investment calculator ────────────────────────────────────────────────────

function holdEstimate(pct: number, horizon?: string): string {
  if (horizon === "5-10yr") {
    if (pct < 50)  return "3–5 years";
    if (pct < 150) return "5–8 years";
    return "8–10+ years";
  }
  if (horizon === "3-5yr") {
    if (pct < 20)  return "6–12 months";
    if (pct < 60)  return "1–3 years";
    return "3–5 years";
  }
  if (pct < 5)  return "3–6 months";
  if (pct < 20) return "6–12 months";
  if (pct < 40) return "1–2 years";
  return "2–3 years";
}

function InvestmentCalculator({ pick, onSimulate }: { pick: any; onSimulate?: () => void }) {
  const [amount, setAmount] = useState("1000");
  const [profitGoal, setProfitGoal] = useState("5");

  const investment = Math.max(0, parseFloat(amount) || 0);
  const goalAmt = Math.max(0.01, parseFloat(profitGoal) || 5);
  const midEntry = pick.entry_low && pick.entry_high ? (pick.entry_low + pick.entry_high) / 2 : 0;
  const shares = midEntry > 0 && investment > 0 ? +(investment / midEntry).toFixed(6) : 0;

  const gainAtTarget = shares > 0 && pick.target    ? shares * (pick.target - midEntry)    : 0;
  const lossAtStop   = shares > 0 && pick.stop_loss ? shares * (midEntry - pick.stop_loss) : 0;
  const priceToGoal  = shares > 0                   ? midEntry + goalAmt / shares           : 0;
  const pctToGoal    = midEntry > 0 && shares > 0   ? (goalAmt / shares / midEntry) * 100   : 0;
  const pctToTarget  = midEntry > 0 && pick.target  ? ((pick.target - midEntry) / midEntry) * 100 : 0;
  const returnPct    = midEntry > 0 && pick.target  ? ((pick.target - midEntry) / midEntry * 100).toFixed(1) : "—";
  const hz = pick.hold_horizon;

  return (
    <div className="px-4 pb-4 pt-3 bg-zinc-950/70 border-t border-cyan-900/30 space-y-3">
      <div className="flex items-center gap-3 flex-wrap">
        <span className="text-xs font-semibold text-zinc-300">Return Estimator</span>
        <div className="flex items-center gap-1.5">
          <span className="text-xs text-zinc-500">Invest</span>
          <div className="relative">
            <span className="absolute left-2.5 top-1/2 -translate-y-1/2 text-xs text-zinc-500">$</span>
            <input
              type="number" min="0" step="100" value={amount}
              onChange={(e) => setAmount(e.target.value)}
              className="w-28 pl-5 pr-2 py-1.5 bg-zinc-800 border border-zinc-700 rounded-lg text-sm text-zinc-200 focus:outline-none focus:border-cyan-600 tabular-nums"
            />
          </div>
        </div>
        {shares > 0 && (
          <span className="text-xs text-zinc-600 tabular-nums">
            → {shares < 1 ? shares.toFixed(4) : shares.toFixed(2)} shares @ {formatPrice(midEntry)}
          </span>
        )}
      </div>

      {shares > 0 ? (
        <>
          <div className="grid grid-cols-1 sm:grid-cols-3 gap-2">
            <div className="bg-zinc-900 rounded-lg p-3 border border-cyan-900/30">
              <div className="text-[10px] text-zinc-500 uppercase tracking-wider mb-1.5 flex items-center gap-1">
                Hit
                <div className="relative inline-flex items-center">
                  <span className="absolute left-1.5 text-[10px] text-zinc-500 pointer-events-none">$</span>
                  <input
                    type="number" min="0.01" step="1" value={profitGoal}
                    onChange={(e) => setProfitGoal(e.target.value)}
                    className="w-14 pl-4 pr-1 py-0.5 bg-zinc-800 border border-zinc-700 rounded text-[10px] text-cyan-300 focus:outline-none focus:border-cyan-600 tabular-nums"
                  />
                </div>
                profit when
              </div>
              <div className="text-sm font-bold text-cyan-300 tabular-nums">{formatPrice(priceToGoal)}</div>
              <div className="text-[10px] text-zinc-500 mt-1">
                +{pctToGoal.toFixed(2)}% · est. <span className="text-zinc-400">{holdEstimate(pctToGoal, hz)}</span>
              </div>
            </div>
            <div className="bg-zinc-900 rounded-lg p-3 border border-emerald-900/40">
              <div className="text-[10px] text-zinc-500 uppercase tracking-wider mb-1.5">At target ({formatPrice(pick.target)})</div>
              <div className={`text-sm font-bold tabular-nums ${gainAtTarget >= 0 ? "text-emerald-400" : "text-red-400"}`}>
                {gainAtTarget >= 0 ? "+" : "−"}${Math.abs(gainAtTarget).toFixed(2)}
                <span className="text-xs font-normal text-zinc-600 ml-1">({returnPct}%)</span>
              </div>
              <div className="text-[10px] text-zinc-500 mt-1">
                +{pctToTarget.toFixed(1)}% · est. <span className="text-zinc-400">{holdEstimate(pctToTarget, hz)}</span>
              </div>
            </div>
            <div className="bg-zinc-900 rounded-lg p-3 border border-red-900/30">
              <div className="text-[10px] text-zinc-500 uppercase tracking-wider mb-1.5">Stop loss ({formatPrice(pick.stop_loss)})</div>
              <div className="text-sm font-bold text-red-400 tabular-nums">−${lossAtStop.toFixed(2)}</div>
              <div className="text-[10px] text-zinc-500 mt-1">max loss if stop is hit</div>
            </div>
          </div>
          {pctToTarget > 0 && (
            <p className="text-[10px] text-zinc-600">
              Min to make ${goalAmt % 1 === 0 ? goalAmt.toFixed(0) : goalAmt.toFixed(2)} at target:{" "}
              <span className="text-zinc-400 tabular-nums">${(goalAmt / (pctToTarget / 100)).toFixed(2)}</span>
              {hz === "5-10yr"
                ? " · Decade-long holds — conviction in the business matters more than short-term price action."
                : hz === "3-5yr"
                  ? " · Multi-year holds — focus on business quality and patience."
                  : " · Hold estimates based on target % move — actual timing depends on catalysts."}
            </p>
          )}
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

// ─── Pick detail card ─────────────────────────────────────────────────────────

function PickCard({ pick, onSelect, onSimulate }: { pick: any; onSelect: () => void; onSimulate?: () => void }) {
  const [calcOpen, setCalcOpen] = useState(false);
  const tradeTypeClass = TRADE_TYPE_COLORS[pick.trade_type] || "bg-zinc-800 text-zinc-400 border-zinc-700";
  const confidenceColor =
    pick.confidence >= 8 ? "text-emerald-400" : pick.confidence >= 6 ? "text-yellow-400" : "text-red-400";
  const risk = pick.entry_high && pick.stop_loss ? pick.entry_high - pick.stop_loss : null;
  const reward = pick.entry_low && pick.target ? pick.target - pick.entry_low : null;

  return (
    <div className={`bg-zinc-900 border rounded-xl overflow-hidden transition-colors ${calcOpen ? "border-cyan-800/50" : "border-zinc-800 hover:border-zinc-700"}`}>
      <div className="flex items-center justify-between px-4 py-3 border-b border-zinc-800/60">
        <div className="flex items-center gap-2 flex-wrap">
          <span className="text-xl font-bold text-cyan-400">#{pick.rank}</span>
          <button onClick={onSelect} className="font-bold text-lg text-zinc-100 hover:text-cyan-400 transition-colors">{pick.ticker}</button>
          {pick.hold_horizon && <HorizonBadge horizon={pick.hold_horizon} />}
          {pick.trade_type && (
            <span className={`text-[10px] px-2 py-0.5 rounded border ${tradeTypeClass}`}>{pick.trade_type}</span>
          )}
        </div>
        <div className="flex items-center gap-2">
          <div className={`text-sm font-bold tabular-nums ${confidenceColor}`}>
            {pick.confidence}/10
            <span className="text-xs font-normal text-zinc-600 ml-1">confidence</span>
          </div>
          <button
            onClick={() => setCalcOpen((o) => !o)}
            className={`flex items-center gap-1 text-xs border px-2.5 py-1 rounded-lg transition-colors ${
              calcOpen ? "bg-cyan-600/20 border-cyan-600/40 text-cyan-400" : "bg-zinc-800 border-zinc-700 text-zinc-400 hover:text-cyan-400 hover:border-cyan-800"
            }`}
          >
            $ Returns {calcOpen ? <ChevronUp size={11} /> : <ChevronDown size={11} />}
          </button>
        </div>
      </div>
      <div className="grid grid-cols-4 gap-0 divide-x divide-zinc-800">
        <PriceTile label="Entry Zone" value={`${formatPrice(pick.entry_low)} – ${formatPrice(pick.entry_high)}`} className="text-zinc-200" />
        <PriceTile label="Stop Loss" value={formatPrice(pick.stop_loss)} className="text-red-400" />
        <PriceTile label="Target" value={formatPrice(pick.target)} className="text-emerald-400" />
        <PriceTile label="Risk/Reward" value={pick.risk_reward || (risk && reward ? `1:${(reward / risk).toFixed(1)}` : "—")} className="text-cyan-400" />
      </div>
      <div className="px-4 py-1.5 border-t border-zinc-800/40">
        <div className="h-1 bg-zinc-800 rounded-full overflow-hidden">
          <div
            className={`h-full rounded-full transition-all ${pick.confidence >= 8 ? "bg-emerald-500" : pick.confidence >= 6 ? "bg-yellow-500" : "bg-red-500"}`}
            style={{ width: `${(pick.confidence / 10) * 100}%` }}
          />
        </div>
      </div>
      <div className="px-4 pt-3 pb-2">
        <p className="text-sm text-zinc-400 leading-relaxed">{pick.thesis}</p>
      </div>
      {(pick.catalyst || pick.key_risk) && (
        <div className="px-4 pb-3 space-y-1">
          {pick.catalyst && (
            <div className="flex items-start gap-1.5">
              <Target size={10} className="text-cyan-500 shrink-0 mt-0.5" />
              <p className="text-[11px] text-zinc-500 leading-snug">{pick.catalyst}</p>
            </div>
          )}
          {pick.key_risk && (
            <div className="flex items-start gap-1.5">
              <ShieldAlert size={10} className="text-amber-500/80 shrink-0 mt-0.5" />
              <p className="text-[11px] text-zinc-500 leading-snug">{pick.key_risk}</p>
            </div>
          )}
        </div>
      )}
      {calcOpen && <InvestmentCalculator pick={pick} onSimulate={onSimulate} />}
    </div>
  );
}

// ─── Ticker analysis card ─────────────────────────────────────────────────────

function TickerAnalysisCard({ analysis, onSelect, onSimulate }: { analysis: any; onSelect: () => void; onSimulate?: () => void }) {
  const [calcOpen, setCalcOpen] = useState(false);
  const rec = analysis.recommendation?.toLowerCase() as "buy" | "hold" | "avoid";
  const recConf = REC_CONFIG[rec] ?? REC_CONFIG.hold;
  const confidenceColor =
    analysis.confidence >= 8 ? "text-emerald-400" : analysis.confidence >= 6 ? "text-yellow-400" : "text-red-400";
  const hz = analysis.hold_horizon;

  return (
    <div className={`rounded-xl border overflow-hidden ${recConf.bg.replace("border-", "border-")}`}>
      <div className={`flex items-center justify-between px-4 py-3 border-b border-zinc-800/60 ${recConf.bg}`}>
        <div className="flex items-center gap-2 flex-wrap">
          <button onClick={onSelect} className="font-bold text-lg text-zinc-100 hover:text-cyan-400 transition-colors">{analysis.ticker}</button>
          <span className={`flex items-center gap-1 text-xs font-bold px-2.5 py-1 rounded-lg border ${recConf.bg} ${recConf.cls}`}>
            {recConf.icon} {recConf.label}
          </span>
          {hz && <HorizonBadge horizon={hz} />}
        </div>
        <div className="flex items-center gap-2">
          <div className={`text-sm font-bold tabular-nums ${confidenceColor}`}>
            {analysis.confidence}/10
            <span className="text-xs font-normal text-zinc-600 ml-1">confidence</span>
          </div>
          <button
            onClick={() => setCalcOpen((o) => !o)}
            className={`flex items-center gap-1 text-xs border px-2.5 py-1 rounded-lg transition-colors ${
              calcOpen ? "bg-cyan-600/20 border-cyan-600/40 text-cyan-400" : "bg-zinc-800 border-zinc-700 text-zinc-400 hover:text-cyan-400 hover:border-cyan-800"
            }`}
          >
            $ Returns {calcOpen ? <ChevronUp size={11} /> : <ChevronDown size={11} />}
          </button>
        </div>
      </div>
      <div className="grid grid-cols-4 gap-0 divide-x divide-zinc-800 bg-zinc-900/60">
        <PriceTile label="Entry Zone" value={`${formatPrice(analysis.entry_low)} – ${formatPrice(analysis.entry_high)}`} className="text-zinc-200" />
        <PriceTile label="Stop Loss" value={formatPrice(analysis.stop_loss)} className="text-red-400" />
        <PriceTile label="Target" value={formatPrice(analysis.target)} className="text-emerald-400" />
        <PriceTile label="Risk/Reward" value={analysis.risk_reward || "—"} className="text-cyan-400" />
      </div>
      <div className="px-4 py-1.5 bg-zinc-900/40 border-t border-zinc-800/40">
        <div className="h-1 bg-zinc-800 rounded-full overflow-hidden">
          <div
            className={`h-full rounded-full transition-all ${analysis.confidence >= 8 ? "bg-emerald-500" : analysis.confidence >= 6 ? "bg-yellow-500" : "bg-red-500"}`}
            style={{ width: `${(analysis.confidence / 10) * 100}%` }}
          />
        </div>
      </div>
      <div className="px-4 pt-3 pb-2 bg-zinc-900/40">
        <p className="text-sm text-zinc-400 leading-relaxed">{analysis.thesis}</p>
        <p className="text-[10px] text-zinc-600 italic mt-2">
          {hz ? `Long-term analysis (${HORIZON_LABELS[hz] ?? hz} horizon) · not financial advice` : "Long-term analysis · not financial advice"}
        </p>
      </div>
      {(analysis.catalyst || analysis.key_risk) && (
        <div className="px-4 pb-3 bg-zinc-900/40 space-y-1">
          {analysis.catalyst && (
            <div className="flex items-start gap-1.5">
              <Target size={10} className="text-cyan-500 shrink-0 mt-0.5" />
              <p className="text-[11px] text-zinc-500 leading-snug">{analysis.catalyst}</p>
            </div>
          )}
          {analysis.key_risk && (
            <div className="flex items-start gap-1.5">
              <ShieldAlert size={10} className="text-amber-500/80 shrink-0 mt-0.5" />
              <p className="text-[11px] text-zinc-500 leading-snug">{analysis.key_risk}</p>
            </div>
          )}
        </div>
      )}
      {calcOpen && <InvestmentCalculator pick={analysis} onSimulate={onSimulate} />}
    </div>
  );
}

// ─── Error renderer ───────────────────────────────────────────────────────────

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

// ─── Reusable picks panel ─────────────────────────────────────────────────────

function PicksPanel({
  mode,
  label,
  description,
  accentCls,
  data,
  loading,
  onTickerSelect,
  onSimulate,
}: {
  mode: "unified" | "bargain";
  label: string;
  description: string;
  accentCls: string;
  data: any;
  loading: boolean;
  onTickerSelect: (t: string) => void;
  onSimulate?: (t: string) => void;
}) {
  const [page, setPage] = useState(0);
  const [page1Picks, setPage1Picks] = useState<any[]>([]);
  const [loadingPage1, setLoadingPage1] = useState(false);
  const [horizonFilter, setHorizonFilter] = useState<HorizonFilter>("all");
  const [expandedPick, setExpandedPick] = useState<string | null>(null);
  const [retrying, setRetrying] = useState(false);
  const [override, setOverride] = useState<any>(null);

  const modeData = override ?? data;
  const page0Picks: any[] = modeData?.picks ?? [];
  const hasPage1 = modeData?.has_more ?? false;
  const totalPages = hasPage1 || page1Picks.length > 0 ? 2 : 1;

  // Reset when data changes (new fetch)
  useEffect(() => {
    setPage(0);
    setPage1Picks([]);
    setHorizonFilter("all");
    setExpandedPick(null);
  }, [data]);

  const currentPagePicks = page === 0 ? page0Picks : page1Picks;

  // Count horizons across all loaded picks
  const allKnownPicks = [...page0Picks, ...page1Picks];
  const horizonCounts: Record<HorizonFilter, number> = { all: allKnownPicks.length, "1-3yr": 0, "3-5yr": 0, "5-10yr": 0 };
  for (const p of allKnownPicks) {
    const h = p.hold_horizon as HorizonFilter;
    if (h && h in horizonCounts) horizonCounts[h]++;
  }

  const filteredPicks = horizonFilter === "all"
    ? currentPagePicks
    : currentPagePicks.filter((p) => p.hold_horizon === horizonFilter);

  const handleNextPage = async () => {
    if (page === 1) return;
    if (page1Picks.length === 0 && hasPage1) {
      setLoadingPage1(true);
      try {
        const result = await api.aiPicksMore(mode) as any;
        setPage1Picks(result.picks ?? []);
      } catch {}
      finally { setLoadingPage1(false); }
    }
    setPage(1);
  };

  const handleRetry = async () => {
    if (retrying) return;
    setRetrying(true);
    try {
      // Clear any stale empty cache for this mode before re-fetching
      await api.aiClearMode(mode);
      const result = await api.aiPicks(mode) as any;
      if (result?.picks?.length > 0) setOverride(result);
    } catch {}
    finally { setRetrying(false); }
  };

  const isLoading = loading || retrying;

  return (
    <div className="bg-zinc-900 border border-zinc-800 rounded-xl overflow-hidden">
      {/* Header */}
      <div className="flex items-center justify-between px-4 py-3 border-b border-zinc-800 gap-3 flex-wrap">
        <div className="flex items-center gap-2 shrink-0">
          <span className={`font-semibold text-sm ${accentCls}`}>{label}</span>
          <span className="text-[10px] text-zinc-500 border border-zinc-700 rounded px-1.5 py-0.5">{description}</span>
          {allKnownPicks.length > 0 && !isLoading && (
            <span className="text-[10px] text-zinc-600">{allKnownPicks.length} picks</span>
          )}
          {modeData?.bias && (
            <span className={`text-xs ${
              modeData.bias === "bullish" ? "text-emerald-400" :
              modeData.bias === "bearish" ? "text-red-400" : "text-yellow-400"
            }`}>{modeData.bias}</span>
          )}
        </div>
        {allKnownPicks.length > 0 && (
          <HorizonFilterBar value={horizonFilter} counts={horizonCounts} onChange={setHorizonFilter} />
        )}
      </div>

      {isLoading && (
        <div className="px-4 py-3 space-y-2 animate-pulse">
          {[...Array(4)].map((_, i) => <div key={i} className="h-8 bg-zinc-800 rounded" />)}
        </div>
      )}

      {modeData && !isLoading && (
        <div className="px-4 py-3 space-y-3">
          {modeData.market_summary && (
            <p className="text-xs text-zinc-400 leading-relaxed">{modeData.market_summary}</p>
          )}

          {page0Picks.length === 0 && (
            <div className="flex items-center gap-3">
              <p className="text-xs text-zinc-600 italic">Analysis temporarily unavailable.</p>
              <button
                onClick={handleRetry}
                disabled={retrying}
                className="flex items-center gap-1 text-[10px] text-zinc-500 hover:text-cyan-400 border border-zinc-700 hover:border-cyan-700 px-2 py-1 rounded transition-colors disabled:opacity-40"
              >
                <RefreshCw size={10} className={retrying ? "animate-spin" : ""} />
                {retrying ? "Retrying…" : "Retry"}
              </button>
            </div>
          )}

          {filteredPicks.length === 0 && page0Picks.length > 0 && (
            <p className="text-xs text-zinc-600 italic text-center py-2">No picks for this horizon on page {page + 1}.</p>
          )}

          {filteredPicks.length > 0 && (
            <div className="space-y-1.5">
              {filteredPicks.map((pick: any) => {
                const key = `${mode}-${pick.ticker}-${pick.rank}`;
                const isExpanded = expandedPick === key;
                return (
                  <div key={key} className="rounded-xl border border-zinc-800 overflow-hidden">
                    <div className="flex items-center justify-between bg-zinc-800/60 px-3 py-2 gap-2">
                      <div className="flex items-center gap-2 min-w-0">
                        <span className="text-xs text-zinc-600 shrink-0">#{pick.rank}</span>
                        <button
                          onClick={() => onTickerSelect(pick.ticker)}
                          className={`font-bold text-sm shrink-0 ${accentCls} hover:underline`}
                        >
                          {pick.ticker}
                        </button>
                        {pick.hold_horizon && <HorizonBadge horizon={pick.hold_horizon} />}
                        <span className="text-xs text-zinc-500 truncate hidden md:block">{pick.thesis?.slice(0, 70)}…</span>
                      </div>
                      <div className="flex items-center gap-2 shrink-0">
                        <span className={`text-xs font-bold tabular-nums ${
                          pick.confidence >= 8 ? "text-emerald-400" : pick.confidence >= 6 ? "text-yellow-400" : "text-red-400"
                        }`}>{pick.confidence}/10</span>
                        <button
                          onClick={() => {
                            const next = isExpanded ? null : key;
                            setExpandedPick(next);
                            if (!isExpanded) onTickerSelect(pick.ticker);
                          }}
                          className="flex items-center gap-0.5 text-[10px] text-zinc-500 hover:text-zinc-300 px-1.5 py-0.5 rounded transition-colors"
                        >
                          Detail {isExpanded ? <ChevronUp size={10} /> : <ChevronDown size={10} />}
                        </button>
                      </div>
                    </div>
                    {isExpanded && (
                      <PickCard
                        pick={pick}
                        onSelect={() => onTickerSelect(pick.ticker)}
                        onSimulate={onSimulate ? () => onSimulate(pick.ticker) : undefined}
                      />
                    )}
                  </div>
                );
              })}
            </div>
          )}

          {/* Pagination */}
          {totalPages > 1 && page0Picks.length > 0 && (
            <div className="flex items-center justify-center gap-3 pt-2 border-t border-zinc-800/60">
              <button
                onClick={() => setPage(0)}
                disabled={page === 0}
                className="flex items-center gap-1 text-xs text-zinc-500 hover:text-zinc-300 disabled:opacity-30 px-2 py-1 rounded transition-colors"
              >
                <ChevronLeft size={12} /> Prev
              </button>
              <span className="text-xs text-zinc-500 tabular-nums">
                Page {page + 1} / {totalPages}
              </span>
              <button
                onClick={handleNextPage}
                disabled={page === totalPages - 1 || loadingPage1}
                className="flex items-center gap-1 text-xs text-zinc-500 hover:text-zinc-300 disabled:opacity-30 px-2 py-1 rounded transition-colors"
              >
                {loadingPage1 ? (
                  <><RefreshCw size={10} className="animate-spin" /> Loading…</>
                ) : (
                  <>Next <ChevronRight size={12} /></>
                )}
              </button>
            </div>
          )}
        </div>
      )}
    </div>
  );
}

// ─── Root component ───────────────────────────────────────────────────────────

function AllPicks({ onTickerSelect, onSimulate }: { onTickerSelect: (t: string) => void; onSimulate?: (t: string) => void }) {
  const [fetchKey, setFetchKey] = useState(0);
  const [tickerInput, setTickerInput] = useState("");
  const [tickerAnalysis, setTickerAnalysis] = useState<any>(null);
  const [tickerLoading, setTickerLoading] = useState(false);
  const [tickerError, setTickerError] = useState<string | null>(null);
  const [analysisOpen, setAnalysisOpen] = useState(true);

  const { data: allData, loading, error, refetch } = useData(
    () => api.aiPicksAll() as Promise<any>,
    [fetchKey],
    { refreshInterval: 0 }
  );

  const [loadingSeconds, setLoadingSeconds] = useState(0);
  const timerRef = useRef<ReturnType<typeof setInterval> | null>(null);
  useEffect(() => {
    if (loading) {
      setLoadingSeconds(0);
      timerRef.current = setInterval(() => setLoadingSeconds((s) => s + 1), 1000);
    } else {
      if (timerRef.current) clearInterval(timerRef.current);
      setLoadingSeconds(0);
    }
    return () => { if (timerRef.current) clearInterval(timerRef.current); };
  }, [loading]);

  const handleAnalyzeTicker = async () => {
    const t = tickerInput.trim().toUpperCase();
    if (!t) return;
    setTickerLoading(true);
    setTickerError(null);
    setTickerAnalysis(null);
    try {
      const result = await api.analyzeTickerAll(t) as any;
      if (result?.error) throw new Error(result.error);
      setTickerAnalysis(result);
      setAnalysisOpen(true);
      onTickerSelect(t);
    } catch (e) {
      setTickerError(e instanceof Error ? e.message : "Analysis failed");
    } finally {
      setTickerLoading(false);
    }
  };

  const handleRefresh = async () => {
    try { await api.aiRefresh(); } catch {}
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
        </div>
        <div className="flex gap-2">
          <div className="relative flex-1">
            <input
              type="text"
              placeholder="Enter a ticker — get a long-term horizon analysis"
              value={tickerInput}
              onChange={(e) => setTickerInput(e.target.value.toUpperCase())}
              onKeyDown={(e) => e.key === "Enter" && handleAnalyzeTicker()}
              maxLength={10}
              className="w-full bg-zinc-800 border border-zinc-700 rounded-lg px-3 py-2 text-sm text-zinc-200 placeholder-zinc-600 focus:outline-none focus:border-cyan-500 transition-colors pr-7"
            />
            {tickerInput && (
              <button
                onClick={() => { setTickerInput(""); setTickerAnalysis(null); setTickerError(null); }}
                className="absolute right-2 top-1/2 -translate-y-1/2 text-zinc-500 hover:text-zinc-300 transition-colors"
                tabIndex={-1}
              >
                <XCircle size={14} />
              </button>
            )}
          </div>
          <button
            onClick={handleAnalyzeTicker}
            disabled={tickerLoading || !tickerInput.trim()}
            className="px-4 py-2 bg-cyan-600/20 border border-cyan-600/30 text-cyan-400 text-sm rounded-lg hover:bg-cyan-600/30 transition-colors disabled:opacity-40 whitespace-nowrap"
          >
            {tickerLoading ? "Analyzing…" : "Analyze"}
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
          <div className="mt-3">
            <button
              onClick={() => setAnalysisOpen((o) => !o)}
              className="w-full flex items-center justify-between px-3 py-2 bg-zinc-800/60 rounded-lg border border-zinc-700/50 hover:border-zinc-600 transition-colors mb-2"
            >
              <div className="flex items-center gap-2">
                <span className="text-xs font-semibold text-zinc-300">{tickerAnalysis.ticker} — Analysis</span>
                {tickerAnalysis.unified?.hold_horizon && <HorizonBadge horizon={tickerAnalysis.unified.hold_horizon} />}
              </div>
              <span className="text-xs text-zinc-500 flex items-center gap-1">
                {analysisOpen ? "Collapse" : "Expand"}
                {analysisOpen ? <ChevronUp size={12} /> : <ChevronDown size={12} />}
              </span>
            </button>
            {analysisOpen && tickerAnalysis.unified && (
              <TickerAnalysisCard
                analysis={tickerAnalysis.unified}
                onSelect={() => onTickerSelect(tickerAnalysis.unified.ticker)}
                onSimulate={onSimulate ? () => onSimulate(tickerAnalysis.unified.ticker) : undefined}
              />
            )}
          </div>
        )}
      </div>

      {/* Header bar */}
      <div className="flex items-center justify-between px-1">
        <div className="flex items-center gap-2">
          <Sparkles size={14} className="text-zinc-400" />
          <span className="text-sm font-semibold text-zinc-200">AI Picks</span>
          {allData && !loading && (
            <span className="text-[10px] text-zinc-600 border border-zinc-700 rounded px-1.5 py-0.5">
              {allData.unified?.generated_at ?? ""}
            </span>
          )}
        </div>
        <div className="flex flex-col items-end gap-0.5">
          <button
            onClick={handleRefresh}
            disabled={loading}
            className="flex items-center gap-1.5 text-xs text-zinc-400 hover:text-cyan-400 transition-colors disabled:opacity-40"
          >
            <RefreshCw size={12} className={loading ? "animate-spin" : ""} />
            {loading ? `Analyzing… ${loadingSeconds > 0 ? `${loadingSeconds}s` : ""}` : "Refresh"}
          </button>
          {loading && loadingSeconds >= 10 && (
            <span className="text-[10px] text-zinc-600 text-right">
              {loadingSeconds < 60 ? "AI warming up — usually 45–120s" : "Almost there…"}
            </span>
          )}
        </div>
      </div>

      {error && renderError(error)}

      {/* Pick List */}
      <PicksPanel
        mode="unified"
        label="Pick List"
        description="long-term quality"
        accentCls="text-cyan-400"
        data={allData?.unified}
        loading={loading}
        onTickerSelect={onTickerSelect}
        onSimulate={onSimulate}
      />

      {/* Bargain Buys */}
      <PicksPanel
        mode="bargain"
        label="Bargain Buys"
        description="value & undervalued"
        accentCls="text-emerald-400"
        data={allData?.bargain}
        loading={loading}
        onTickerSelect={onTickerSelect}
        onSimulate={onSimulate}
      />

      <p className="text-[10px] text-zinc-700 italic px-1">
        AI-generated for simulation purposes only. Not financial advice. Always verify independently.
      </p>
    </div>
  );
}
