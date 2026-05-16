"use client";
import { useData } from "@/hooks/useData";
import { api } from "@/lib/api";
import { formatPrice } from "@/lib/utils";
import { AlertTriangle, TrendingUp, TrendingDown, Minus } from "lucide-react";

interface FundamentalsPanelProps {
  ticker: string;
}

function fmt(v: number | null | undefined, decimals = 2): string {
  if (v == null) return "—";
  return v.toFixed(decimals);
}

function fmtPct(v: number | null | undefined): string {
  if (v == null) return "—";
  return `${(v * 100).toFixed(1)}%`;
}

function fmtLargeNum(v: number | null | undefined): string {
  if (v == null) return "—";
  if (Math.abs(v) >= 1e12) return `$${(v / 1e12).toFixed(2)}T`;
  if (Math.abs(v) >= 1e9)  return `$${(v / 1e9).toFixed(2)}B`;
  if (Math.abs(v) >= 1e6)  return `$${(v / 1e6).toFixed(2)}M`;
  return `$${v.toFixed(0)}`;
}

function growthColor(v: number | null | undefined): string {
  if (v == null) return "text-zinc-400";
  if (v > 0.1) return "text-emerald-400";
  if (v > 0)   return "text-emerald-300";
  if (v > -0.1) return "text-yellow-400";
  return "text-red-400";
}

function GrowthIcon({ v }: { v: number | null | undefined }) {
  if (v == null) return <Minus size={12} className="text-zinc-600" />;
  if (v > 0) return <TrendingUp size={12} className="text-emerald-400" />;
  return <TrendingDown size={12} className="text-red-400" />;
}

function MetricTile({
  label,
  value,
  valueClass = "text-zinc-200",
  sub,
  highlight,
}: {
  label: string;
  value: string;
  valueClass?: string;
  sub?: string;
  highlight?: "good" | "bad" | "neutral";
}) {
  const borderCls = highlight === "good" ? "border-emerald-900/40" :
                    highlight === "bad"  ? "border-red-900/40" : "border-zinc-800";
  return (
    <div className={`bg-zinc-900 rounded-lg p-3 border ${borderCls}`}>
      <div className="text-[10px] text-zinc-500 uppercase tracking-wider mb-1">{label}</div>
      <div className={`text-sm font-semibold tabular-nums ${valueClass}`}>{value}</div>
      {sub && <div className="text-[10px] text-zinc-600 mt-0.5">{sub}</div>}
    </div>
  );
}

export default function FundamentalsPanel({ ticker }: FundamentalsPanelProps) {
  const { data, loading, error } = useData(
    () => api.fundamentals(ticker) as Promise<any>,
    [ticker],
    { refreshInterval: 0 }
  );

  if (loading) {
    return (
      <div className="bg-zinc-900 border border-zinc-800 rounded-xl p-4 animate-pulse space-y-3">
        <div className="h-4 bg-zinc-800 rounded w-48" />
        <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
          {Array.from({ length: 8 }).map((_, i) => (
            <div key={i} className="h-16 bg-zinc-800 rounded-lg" />
          ))}
        </div>
      </div>
    );
  }

  if (error || !data) {
    return (
      <div className="bg-zinc-900 border border-zinc-800 rounded-xl p-4 flex items-center gap-2 text-sm text-red-400">
        <AlertTriangle size={14} />
        {error ? `Could not load fundamentals: ${error}` : "No fundamental data available."}
      </div>
    );
  }

  const d = data;

  // Valuation health signals
  const peHighlight = d.pe_ratio == null ? "neutral" :
    d.pe_ratio < 15 ? "good" : d.pe_ratio > 40 ? "bad" : "neutral";
  const pegHighlight = d.peg_ratio == null ? "neutral" :
    d.peg_ratio < 1 ? "good" : d.peg_ratio > 2 ? "bad" : "neutral";
  const revGrowthHighlight = d.revenue_growth == null ? "neutral" :
    d.revenue_growth > 0.1 ? "good" : d.revenue_growth < 0 ? "bad" : "neutral";
  const marginHighlight = d.profit_margin == null ? "neutral" :
    d.profit_margin > 0.15 ? "good" : d.profit_margin < 0 ? "bad" : "neutral";
  const debtHighlight = d.debt_to_equity == null ? "neutral" :
    d.debt_to_equity < 50 ? "good" : d.debt_to_equity > 150 ? "bad" : "neutral";

  const week52Range = d.week_52_high && d.week_52_low
    ? `${formatPrice(d.week_52_low)} – ${formatPrice(d.week_52_high)}`
    : "—";

  return (
    <div className="space-y-4">
      {/* Header */}
      <div className="flex items-center gap-2 px-1">
        <TrendingUp size={14} className="text-purple-400" />
        <span className="text-sm font-semibold text-zinc-200">Fundamental Analysis — {ticker.toUpperCase()}</span>
        <span className="text-xs text-zinc-600 border border-zinc-700 rounded px-1.5 py-0.5">Long-Term</span>
      </div>

      {/* Valuation */}
      <div>
        <div className="text-[10px] text-zinc-500 uppercase tracking-wider mb-2 px-1">Valuation</div>
        <div className="grid grid-cols-2 sm:grid-cols-4 gap-2">
          <MetricTile
            label="Trailing P/E"
            value={d.pe_ratio != null ? fmt(d.pe_ratio, 1) : "—"}
            valueClass={d.pe_ratio != null && d.pe_ratio < 15 ? "text-emerald-400" : d.pe_ratio != null && d.pe_ratio > 40 ? "text-red-400" : "text-zinc-200"}
            highlight={peHighlight}
            sub={d.pe_ratio != null ? (d.pe_ratio < 15 ? "Potentially cheap" : d.pe_ratio > 40 ? "Elevated" : "Moderate") : undefined}
          />
          <MetricTile
            label="Forward P/E"
            value={d.forward_pe != null ? fmt(d.forward_pe, 1) : "—"}
            valueClass="text-zinc-200"
          />
          <MetricTile
            label="PEG Ratio"
            value={d.peg_ratio != null ? fmt(d.peg_ratio, 2) : "—"}
            valueClass={d.peg_ratio != null && d.peg_ratio < 1 ? "text-emerald-400" : d.peg_ratio != null && d.peg_ratio > 2 ? "text-red-400" : "text-zinc-200"}
            highlight={pegHighlight}
            sub={d.peg_ratio != null ? (d.peg_ratio < 1 ? "Undervalued vs growth" : d.peg_ratio > 2 ? "Rich vs growth" : "Fair") : undefined}
          />
          <MetricTile label="Price/Book" value={d.pb_ratio != null ? fmt(d.pb_ratio, 1) : "—"} valueClass="text-zinc-200" />
        </div>
      </div>

      {/* Growth */}
      <div>
        <div className="text-[10px] text-zinc-500 uppercase tracking-wider mb-2 px-1">Growth</div>
        <div className="grid grid-cols-2 sm:grid-cols-4 gap-2">
          <div className={`bg-zinc-900 rounded-lg p-3 border ${revGrowthHighlight === "good" ? "border-emerald-900/40" : revGrowthHighlight === "bad" ? "border-red-900/40" : "border-zinc-800"}`}>
            <div className="text-[10px] text-zinc-500 uppercase tracking-wider mb-1">Revenue Growth YoY</div>
            <div className={`flex items-center gap-1 text-sm font-semibold tabular-nums ${growthColor(d.revenue_growth)}`}>
              <GrowthIcon v={d.revenue_growth} />
              {fmtPct(d.revenue_growth)}
            </div>
          </div>
          <div className={`bg-zinc-900 rounded-lg p-3 border ${d.earnings_growth != null && d.earnings_growth > 0.1 ? "border-emerald-900/40" : d.earnings_growth != null && d.earnings_growth < 0 ? "border-red-900/40" : "border-zinc-800"}`}>
            <div className="text-[10px] text-zinc-500 uppercase tracking-wider mb-1">EPS Growth YoY</div>
            <div className={`flex items-center gap-1 text-sm font-semibold tabular-nums ${growthColor(d.earnings_growth)}`}>
              <GrowthIcon v={d.earnings_growth} />
              {fmtPct(d.earnings_growth)}
            </div>
          </div>
          <MetricTile label="Total Revenue" value={fmtLargeNum(d.revenue)} valueClass="text-zinc-200" />
          <MetricTile label="Free Cash Flow" value={fmtLargeNum(d.free_cashflow)}
            valueClass={d.free_cashflow != null && d.free_cashflow > 0 ? "text-emerald-400" : "text-red-400"} />
        </div>
      </div>

      {/* Profitability */}
      <div>
        <div className="text-[10px] text-zinc-500 uppercase tracking-wider mb-2 px-1">Profitability</div>
        <div className="grid grid-cols-2 sm:grid-cols-4 gap-2">
          <MetricTile
            label="Profit Margin"
            value={fmtPct(d.profit_margin)}
            valueClass={d.profit_margin != null && d.profit_margin > 0.15 ? "text-emerald-400" : d.profit_margin != null && d.profit_margin < 0 ? "text-red-400" : "text-zinc-200"}
            highlight={marginHighlight}
          />
          <MetricTile label="Gross Margin" value={fmtPct(d.gross_margins)} valueClass="text-zinc-200" />
          <MetricTile label="Operating Margin" value={fmtPct(d.operating_margin)} valueClass="text-zinc-200" />
          <MetricTile
            label="Return on Equity"
            value={fmtPct(d.roe)}
            valueClass={d.roe != null && d.roe > 0.15 ? "text-emerald-400" : "text-zinc-200"}
          />
        </div>
      </div>

      {/* Balance Sheet */}
      <div>
        <div className="text-[10px] text-zinc-500 uppercase tracking-wider mb-2 px-1">Balance Sheet & Other</div>
        <div className="grid grid-cols-2 sm:grid-cols-4 gap-2">
          <MetricTile
            label="Debt / Equity"
            value={d.debt_to_equity != null ? fmt(d.debt_to_equity, 1) : "—"}
            valueClass={d.debt_to_equity != null && d.debt_to_equity < 50 ? "text-emerald-400" : d.debt_to_equity != null && d.debt_to_equity > 150 ? "text-red-400" : "text-zinc-200"}
            highlight={debtHighlight}
            sub={d.debt_to_equity != null ? (d.debt_to_equity < 50 ? "Low leverage" : d.debt_to_equity > 150 ? "High leverage" : "Moderate") : undefined}
          />
          <MetricTile label="Current Ratio" value={d.current_ratio != null ? fmt(d.current_ratio, 2) : "—"}
            valueClass={d.current_ratio != null && d.current_ratio > 1.5 ? "text-emerald-400" : d.current_ratio != null && d.current_ratio < 1 ? "text-red-400" : "text-zinc-200"} />
          <MetricTile
            label="Dividend Yield"
            value={d.dividend_yield != null && d.dividend_yield > 0 ? fmtPct(d.dividend_yield) : "None"}
            valueClass={d.dividend_yield != null && d.dividend_yield > 0 ? "text-teal-400" : "text-zinc-500"}
          />
          <MetricTile label="52-Week Range" value={week52Range} valueClass="text-zinc-300" />
        </div>
      </div>

      <p className="text-[10px] text-zinc-600 italic px-1">
        Fundamental data sourced from Yahoo Finance. Values may be delayed. Not financial advice.
      </p>
    </div>
  );
}
