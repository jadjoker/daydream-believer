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
    volume?: number | null;
    avg_volume?: number | null;
  };
}

const STATS: { label: string; key: keyof StockInfoBarProps["quote"]; render: (v: any) => string }[] = [
  { label: "Open",         key: "open",          render: (v) => v != null ? formatPrice(v) : "—" },
  { label: "Mkt Cap",      key: "market_cap",    render: fmtCap },
  { label: "Dividend",     key: "dividend_yield", render: fmtPct },
  { label: "High",         key: "day_high",       render: (v) => v != null ? formatPrice(v) : "—" },
  { label: "P/E Ratio",   key: "pe_ratio",       render: (v) => fmt(v) },
  { label: "Qtrly Div",   key: "dividend_rate",  render: (v) => v != null ? `$${fmt(v)}` : "—" },
  { label: "Low",          key: "day_low",        render: (v) => v != null ? formatPrice(v) : "—" },
  { label: "52-wk High",  key: "week_52_high",   render: (v) => v != null ? formatPrice(v) : "—" },
  { label: "52-wk Low",   key: "week_52_low",    render: (v) => v != null ? formatPrice(v) : "—" },
];

export default function StockInfoBar({ quote }: StockInfoBarProps) {
  return (
    <div className="bg-zinc-900 border border-zinc-800 rounded-xl px-4 py-3 mt-2">
      <div className="grid grid-cols-3 gap-x-6 gap-y-1.5">
        {STATS.map(({ label, key, render }) => (
          <div key={label} className="flex items-center justify-between gap-2 min-w-0">
            <span className="text-xs text-zinc-500 shrink-0">{label}</span>
            <span className="text-xs font-medium text-zinc-200 tabular-nums truncate text-right">
              {render(quote[key])}
            </span>
          </div>
        ))}
      </div>
    </div>
  );
}
