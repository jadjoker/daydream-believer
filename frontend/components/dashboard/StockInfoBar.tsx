"use client";
import { formatPrice } from "@/lib/utils";

function fmt(v: number | null | undefined, decimals = 2): string {
  if (v == null) return "—";
  return v.toFixed(decimals);
}

function fmtCap(v: number | null | undefined): string {
  if (v == null) return "—";
  if (v >= 1e12) return `${(v / 1e12).toFixed(2)}T`;
  if (v >= 1e9)  return `${(v / 1e9).toFixed(2)}B`;
  if (v >= 1e6)  return `${(v / 1e6).toFixed(2)}M`;
  return `${v.toFixed(0)}`;
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

const STATS = [
  { label: "Open",        render: (q: StockInfoBarProps["quote"]) => q.open        != null ? formatPrice(q.open)        : "—" },
  { label: "Mkt Cap",     render: (q: StockInfoBarProps["quote"]) => fmtCap(q.market_cap) },
  { label: "Dividend",    render: (q: StockInfoBarProps["quote"]) => fmtPct(q.dividend_yield) },
  { label: "High",        render: (q: StockInfoBarProps["quote"]) => q.day_high     != null ? formatPrice(q.day_high)    : "—" },
  { label: "P/E Ratio",  render: (q: StockInfoBarProps["quote"]) => fmt(q.pe_ratio) },
  { label: "Qtrly Div",  render: (q: StockInfoBarProps["quote"]) => q.dividend_rate != null ? `$${fmt(q.dividend_rate)}` : "—" },
  { label: "Low",         render: (q: StockInfoBarProps["quote"]) => q.day_low      != null ? formatPrice(q.day_low)     : "—" },
  { label: "52-wk High", render: (q: StockInfoBarProps["quote"]) => q.week_52_high  != null ? formatPrice(q.week_52_high): "—" },
  { label: "52-wk Low",  render: (q: StockInfoBarProps["quote"]) => q.week_52_low   != null ? formatPrice(q.week_52_low) : "—" },
];

export default function StockInfoBar({ quote }: StockInfoBarProps) {
  return (
    <div className="bg-zinc-900 border border-zinc-800 rounded-xl px-4 py-3 mt-2">
      <div className="grid grid-cols-3 gap-x-3 gap-y-3">
        {STATS.map(({ label, render }) => (
          <div key={label} className="flex flex-col gap-0.5 min-w-0">
            <span className="text-[10px] text-zinc-500 leading-none">{label}</span>
            <span className="text-xs font-semibold text-zinc-200 tabular-nums truncate">
              {render(quote)}
            </span>
          </div>
        ))}
      </div>
    </div>
  );
}
