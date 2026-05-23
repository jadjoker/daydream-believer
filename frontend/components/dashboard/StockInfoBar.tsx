"use client";
import { formatPrice } from "@/lib/utils";

function fmtCap(v: number | null | undefined): string {
  if (v == null) return "—";
  if (v >= 1e12) return `$${(v / 1e12).toFixed(2)}T`;
  if (v >= 1e9)  return `$${(v / 1e9).toFixed(2)}B`;
  if (v >= 1e6)  return `$${(v / 1e6).toFixed(2)}M`;
  return `$${v.toFixed(0)}`;
}

function fmtPct(v: number | null | undefined): string {
  if (v == null) return "—";
  return `${(v * 100).toFixed(2)}%`;
}

interface StockInfoBarProps {
  quote: {
    open?: number | null;
    day_high?: number | null;
    day_low?: number | null;
    market_cap?: number | null;
    pe_ratio?: number | null;
    week_52_high?: number | null;
    week_52_low?: number | null;
    dividend_yield?: number | null;
    dividend_rate?: number | null;
  };
}

const STATS: { label: string; render: (q: StockInfoBarProps["quote"]) => string }[] = [
  { label: "Open",      render: q => q.open        != null ? formatPrice(q.open)         : "—" },
  { label: "High",      render: q => q.day_high     != null ? formatPrice(q.day_high)     : "—" },
  { label: "Low",       render: q => q.day_low      != null ? formatPrice(q.day_low)      : "—" },
  { label: "Mkt Cap",   render: q => fmtCap(q.market_cap) },
  { label: "P/E",       render: q => q.pe_ratio     != null ? q.pe_ratio.toFixed(1)       : "—" },
  { label: "Div Yield", render: q => fmtPct(q.dividend_yield) },
  { label: "52-wk H",  render: q => q.week_52_high  != null ? formatPrice(q.week_52_high) : "—" },
  { label: "52-wk L",  render: q => q.week_52_low   != null ? formatPrice(q.week_52_low)  : "—" },
  { label: "Div Rate",  render: q => q.dividend_rate != null ? `$${q.dividend_rate.toFixed(2)}` : "—" },
];

export default function StockInfoBar({ quote }: StockInfoBarProps) {
  return (
    <div className="bg-zinc-900/80 border border-zinc-800 rounded-xl px-3 py-2.5 mt-2">
      <div className="grid grid-cols-3 gap-x-2 gap-y-2">
        {STATS.map(({ label, render }) => (
          <div key={label} className="flex flex-col gap-0.5 min-w-0 px-1">
            <span className="text-[10px] text-zinc-600 leading-none">{label}</span>
            <span className="text-xs font-semibold text-zinc-300 tabular-nums truncate">
              {render(quote)}
            </span>
          </div>
        ))}
      </div>
    </div>
  );
}
