"use client";
import { useState, useEffect, useRef } from "react";
import { api } from "@/lib/api";
import { formatPrice } from "@/lib/utils";
import {
  Sparkles, RefreshCw,
  ShieldAlert, Target, ArrowRight, AlertTriangle,
  ChevronDown, ChevronUp,
} from "lucide-react";
import { MetricTooltip } from "./MetricTooltip";

interface AIPicksProps {
  onTickerSelect: (ticker: string) => void;
  onSimulate?: (ticker: string) => void;
}

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

export default function AIPicks({ onTickerSelect, onSimulate }: AIPicksProps) {
  return <AllPicks onTickerSelect={onTickerSelect} onSimulate={onSimulate} />;
}

function timeAgo(generatedAt: string): string {
  // Format: "2026-05-24 12:09 ET"
  const match = generatedAt.match(/(\d{4}-\d{2}-\d{2}) (\d{2}:\d{2})/);
  if (!match) return "";
  const dt = new Date(`${match[1]}T${match[2]}:00-04:00`); // EDT
  if (isNaN(dt.getTime())) return "";
  const diffMin = Math.floor((Date.now() - dt.getTime()) / 60_000);
  if (diffMin < 1) return "just now";
  if (diffMin < 60) return `${diffMin}m ago`;
  const diffHr = Math.floor(diffMin / 60);
  if (diffHr < 24) return `${diffHr}h ago`;
  return `${Math.floor(diffHr / 24)}d ago`;
}

// ─── Price tile ───────────────────────────────────────────────────────────────

function PriceTile({ label, value, className }: { label: string; value: string; className?: string }) {
  return (
    <div className="px-3 py-2.5 text-center">
      <div className="flex items-center justify-center gap-0.5 text-[10px] text-zinc-600 mb-0.5 uppercase tracking-wider">
        {label}<MetricTooltip term={label} />
      </div>
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
          {pick.trade_type && (
            <span className={`text-[10px] px-2 py-0.5 rounded border ${tradeTypeClass}`}>{pick.trade_type}</span>
          )}
        </div>
        <div className="flex items-center gap-2">
          <div className={`flex items-center text-sm font-bold tabular-nums ${confidenceColor}`}>
            {pick.confidence}/10
            <span className="text-xs font-normal text-zinc-600 ml-1">confidence</span>
            <MetricTooltip term="Confidence" />
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

// ─── Error renderer ───────────────────────────────────────────────────────────

function renderError(error: string) {
  const isNoCredits = error.includes("coin jar") || error.includes("credits") || error.includes("billing");
  return (
    <div className="px-4 py-3">
      {isNoCredits ? (
        <div className="rounded-lg border border-amber-700/40 bg-amber-950/20 px-3 py-2 space-y-1">
          <p className="text-xs text-amber-300 font-semibold">Out of AI Credits</p>
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

// ─── Category filter ──────────────────────────────────────────────────────────

type CategoryFilter = "all" | "long_term" | "bargain" | "hidden_gem";

const CATEGORY_TABS: { key: CategoryFilter; label: string }[] = [
  { key: "all",        label: "All" },
  { key: "long_term",  label: "Long Term" },
  { key: "bargain",    label: "Bargain" },
  { key: "hidden_gem", label: "Hidden Gems" },
];

// ─── Picks panel ──────────────────────────────────────────────────────────────

function PicksPanel({
  data,
  loading,
  onTickerSelect,
  onSimulate,
}: {
  data: any;
  loading: boolean;
  onTickerSelect: (t: string) => void;
  onSimulate?: (t: string) => void;
}) {
  const [expandedPick, setExpandedPick] = useState<string | null>(null);
  const [retrying, setRetrying] = useState(false);
  const [override, setOverride] = useState<any>(null);
  const [categoryFilter, setCategoryFilter] = useState<CategoryFilter>("all");

  const modeData = override ?? data;
  const allPicks: any[] = modeData?.picks ?? [];

  const categoryCounts: Record<CategoryFilter, number> = {
    all:        allPicks.length,
    long_term:  allPicks.filter((p: any) => p.category === "long_term").length,
    bargain:    allPicks.filter((p: any) => p.category === "bargain").length,
    hidden_gem: allPicks.filter((p: any) => p.category === "hidden_gem").length,
  };

  const filteredPicks = categoryFilter === "all"
    ? allPicks
    : allPicks.filter((p: any) => p.category === categoryFilter);

  useEffect(() => {
    setExpandedPick(null);
    setCategoryFilter("all");
  }, [data]);

  const handleRetry = async () => {
    if (retrying) return;
    setRetrying(true);
    try {
      await api.aiClearMode("unified");
      const result = await api.aiPicks("unified") as any;
      if (result?.picks?.length > 0) setOverride(result);
    } catch {}
    finally { setRetrying(false); }
  };

  const isLoading = loading || retrying;

  return (
    <div className="bg-zinc-900 border border-zinc-800 rounded-xl overflow-hidden">
      <div className="flex items-center justify-between px-4 py-3 border-b border-zinc-800 gap-3 flex-wrap">
        <div className="flex items-center gap-2 shrink-0">
          <span className="font-semibold text-sm text-cyan-400">Pick List</span>
          {allPicks.length > 0 && !isLoading && (
            <span className="text-[10px] text-zinc-600">{allPicks.length} picks</span>
          )}
          {modeData?.bias && (
            <span className={`text-xs ${
              modeData.bias === "bullish" ? "text-emerald-400" :
              modeData.bias === "bearish" ? "text-red-400" : "text-yellow-400"
            }`}>{modeData.bias}</span>
          )}
        </div>

        {allPicks.length > 0 && !isLoading && (
          <div className="flex items-center gap-1">
            {CATEGORY_TABS.map(({ key, label }) => {
              const count = categoryCounts[key];
              if (key !== "all" && count === 0) return null;
              return (
                <button
                  key={key}
                  onClick={() => setCategoryFilter(key)}
                  className={`text-[10px] px-2 py-0.5 rounded transition-colors ${
                    categoryFilter === key
                      ? "bg-zinc-700 text-zinc-200"
                      : "text-zinc-500 hover:text-zinc-300"
                  }`}
                >
                  {label}{key !== "all" && count > 0 ? ` (${count})` : ""}
                </button>
              );
            })}
          </div>
        )}
      </div>

      {isLoading && (
        <div className="px-4 py-3 space-y-2 animate-pulse">
          {[...Array(4)].map((_, i) => <div key={i} className="h-8 bg-zinc-800 rounded" />)}
        </div>
      )}

      {modeData && !isLoading && (
        <div className="px-4 py-3 space-y-3">
          {allPicks.length === 0 && (
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

          {filteredPicks.length > 0 && (
            <div className="space-y-1.5">
              {filteredPicks.map((pick: any) => {
                const key = `unified-${pick.ticker}-${pick.rank}`;
                const isExpanded = expandedPick === key;
                return (
                  <div key={key} className="rounded-xl border border-zinc-800 overflow-hidden">
                    <div className="flex items-center justify-between bg-zinc-800/60 px-3 py-2 gap-2">
                      <div className="flex items-center gap-2 min-w-0">
                        <span className="text-xs text-zinc-600 shrink-0">#{pick.rank}</span>
                        <button
                          onClick={() => onTickerSelect(pick.ticker)}
                          className="font-bold text-sm shrink-0 text-cyan-400 hover:underline"
                        >
                          {pick.ticker}
                        </button>
                        {pick.category === "bargain" && (
                          <span className="text-[9px] px-1.5 py-0.5 rounded border bg-emerald-500/10 border-emerald-600/30 text-emerald-400 shrink-0 hidden sm:inline">Bargain</span>
                        )}
                        {pick.category === "hidden_gem" && (
                          <span className="text-[9px] px-1.5 py-0.5 rounded border bg-violet-500/10 border-violet-600/30 text-violet-400 shrink-0 hidden sm:inline">Hidden Gem</span>
                        )}
                        <span className="text-xs text-zinc-500 truncate hidden md:block">{pick.thesis?.slice(0, 70)}…</span>
                      </div>
                      <div className="flex items-center gap-2 shrink-0">
                        <span className={`flex items-center text-xs font-bold tabular-nums ${
                          pick.confidence >= 8 ? "text-emerald-400" : pick.confidence >= 6 ? "text-yellow-400" : "text-red-400"
                        }`}>{pick.confidence}/10<MetricTooltip term="Confidence" /></span>
                        <button
                          onClick={() => {
                            const expanding = !isExpanded;
                            setExpandedPick(expanding ? key : null);
                            if (expanding) onTickerSelect(pick.ticker);
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

          {filteredPicks.length === 0 && allPicks.length > 0 && (
            <p className="text-xs text-zinc-600 italic">No picks in this category yet.</p>
          )}
        </div>
      )}
    </div>
  );
}

// ─── Root component ───────────────────────────────────────────────────────────

// Polling interval and max wait before giving up
const POLL_INTERVAL_MS = 4000;
const MAX_WAIT_MS = 120_000; // 2 minutes

type Phase = "checking" | "generating" | "ready" | "error";

function AllPicks({ onTickerSelect, onSimulate }: { onTickerSelect: (t: string) => void; onSimulate?: (t: string) => void }) {
  const [phase, setPhase] = useState<Phase>("checking");
  const [picksData, setPicksData] = useState<any>(null);
  const [errorMsg, setErrorMsg] = useState<string | null>(null);
  const [loadingSeconds, setLoadingSeconds] = useState(0);
  const [runKey, setRunKey] = useState(0);

  const pollRef  = useRef<ReturnType<typeof setInterval> | null>(null);
  const timerRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const startRef = useRef<number>(0);

  const stopPoll = () => { if (pollRef.current) { clearInterval(pollRef.current); pollRef.current = null; } };
  const stopTimer = () => { if (timerRef.current) { clearInterval(timerRef.current); timerRef.current = null; } };

  const loadPicksFromCache = async () => {
    try {
      const data = await api.aiPicksAll() as any;
      setPicksData(data);
      setPhase("ready");
    } catch (e: any) {
      setErrorMsg(e.message || "Failed to load picks");
      setPhase("error");
    }
  };

  const startPolling = () => {
    startRef.current = Date.now();
    stopPoll();
    pollRef.current = setInterval(async () => {
      try {
        const s = await api.aiPicksStatus() as any;
        if (s.has_picks) {
          stopPoll();
          stopTimer();
          loadPicksFromCache();
          return;
        }
        // If generation stopped but no picks → it failed
        if (!s.generating && Date.now() - startRef.current > 20_000) {
          stopPoll();
          stopTimer();
          setErrorMsg("Generation failed — please retry.");
          setPhase("error");
        }
        // Hard timeout
        if (Date.now() - startRef.current > MAX_WAIT_MS) {
          stopPoll();
          stopTimer();
          setErrorMsg("Timed out waiting for picks — please retry.");
          setPhase("error");
        }
      } catch {}
    }, POLL_INTERVAL_MS);
  };

  useEffect(() => {
    setPhase("checking");
    setPicksData(null);
    setErrorMsg(null);
    setLoadingSeconds(0);
    stopPoll();
    stopTimer();

    api.aiPicksStatus().then(async (s: any) => {
      if (s.has_picks) {
        loadPicksFromCache();
      } else {
        // Start background generation, then poll status
        setPhase("generating");
        startRef.current = Date.now();
        timerRef.current = setInterval(() => setLoadingSeconds((n) => n + 1), 1000);
        try { await api.aiRefresh(); } catch {}
        startPolling();
      }
    }).catch(() => {
      // Status check failed — try generating anyway
      setPhase("generating");
      startRef.current = Date.now();
      timerRef.current = setInterval(() => setLoadingSeconds((n) => n + 1), 1000);
      api.aiRefresh().catch(() => {});
      startPolling();
    });

    return () => { stopPoll(); stopTimer(); };
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [runKey]);

  const handleRefresh = async () => {
    stopPoll();
    stopTimer();
    setPhase("generating");
    setPicksData(null);
    setErrorMsg(null);
    setLoadingSeconds(0);
    startRef.current = Date.now();
    timerRef.current = setInterval(() => setLoadingSeconds((n) => n + 1), 1000);
    try { await api.aiRefresh(); } catch {}
    startPolling();
    // Intentionally NOT calling setRunKey — avoids triggering useEffect which would fire a second aiRefresh()
  };

  const generatingMsg = loadingSeconds > 45
    ? "Almost there…"
    : loadingSeconds > 5
    ? `Generating… ${loadingSeconds}s`
    : "Generating picks…";

  const cacheAge = phase === "ready" && picksData?.unified?.generated_at
    ? timeAgo(picksData.unified.generated_at)
    : null;

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between px-1">
        <div className="flex items-center gap-2">
          <Sparkles size={14} className="text-zinc-400" />
          <span className="text-sm font-semibold text-zinc-200">AI Picks</span>
        </div>
        <div className="flex items-center gap-2">
          {phase === "ready" && (
            <>
              {cacheAge && (
                <span className="text-[10px] text-zinc-600">
                  {cacheAge}
                </span>
              )}
              <button
                onClick={handleRefresh}
                className="flex items-center gap-1.5 text-xs text-zinc-400 hover:text-cyan-400 transition-colors"
              >
                <RefreshCw size={12} />
                Refresh
              </button>
            </>
          )}
          {(phase === "checking" || phase === "generating") && (
            <span className="flex items-center gap-1.5 text-xs text-zinc-500">
              <RefreshCw size={10} className="animate-spin" />
              {phase === "generating" ? generatingMsg : "Checking…"}
            </span>
          )}
        </div>
      </div>

      {phase === "error" && errorMsg && renderError(errorMsg)}

      {phase === "checking" && (
        <div className="bg-zinc-900 border border-zinc-800 rounded-xl px-4 py-3 space-y-2 animate-pulse">
          {[...Array(3)].map((_, i) => <div key={i} className="h-8 bg-zinc-800 rounded" />)}
        </div>
      )}

      {(phase === "generating" || phase === "ready") && (
        <PicksPanel
          data={picksData?.unified}
          loading={phase === "generating"}
          onTickerSelect={onTickerSelect}
          onSimulate={onSimulate}
        />
      )}

      <p className="text-[10px] text-zinc-700 italic px-1">
        AI-generated for simulation purposes only. Not financial advice. Always verify independently.
      </p>
    </div>
  );
}
