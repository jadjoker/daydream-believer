"use client";
import { useState, useRef, useEffect } from "react";
import { Info } from "lucide-react";

const DEFS: Record<string, string> = {
  "P/E":         "Price-to-Earnings — how much investors pay per $1 of annual profit. Lower can mean cheaper relative to earnings.",
  "Fwd P/E":     "Forward P/E — like P/E but uses next year's estimated earnings, reflecting expected growth.",
  "FwdP/E":      "Forward P/E — like P/E but uses next year's estimated earnings, reflecting expected growth.",
  "P/S":         "Price-to-Sales — market cap divided by annual revenue. Useful for high-growth or pre-profit companies.",
  "P/B":         "Price-to-Book — market cap vs. net assets on the balance sheet. Below 1 may signal undervaluation.",
  "PEG":         "Price/Earnings-to-Growth — P/E divided by earnings growth rate. Below 1 is often considered attractive.",
  "D/E":         "Debt-to-Equity — total debt divided by shareholder equity. Higher means more financial leverage.",
  "ROE":         "Return on Equity — annual profit as % of shareholder equity. Measures how efficiently management uses capital.",
  "ROA":         "Return on Assets — profit generated per dollar of assets. Measures overall operational efficiency.",
  "FCF":         "Free Cash Flow — cash left after capital expenditures. The real measure of a company's financial health.",
  "RevGrowth":   "Revenue Growth — year-over-year change in total sales.",
  "EPSGrowth":   "EPS Growth — year-over-year change in earnings per share.",
  "GrossMargin": "Gross Margin — revenue minus cost of goods as %. Higher means more pricing power.",
  "OpMargin":    "Operating Margin — profit after operating expenses as %. Shows core business efficiency.",
  "NetMargin":   "Net Margin — final profit as % of revenue after all expenses and taxes.",
  "Div":         "Dividend Yield — annual dividend payment as % of share price.",
  "ShortRatio":  "Short Ratio — days to cover all short positions at current volume. High values can signal a short squeeze setup.",
  "Mkt Cap":     "Market Capitalization — total market value of all shares outstanding (price × shares).",
  "52w Range":   "The stock's high and low trading prices over the past 52 weeks (one year).",
  "Entry":       "Suggested price range to initiate or add to a position.",
  "Entry Zone":  "Suggested price range to initiate or add to a position.",
  "Stop":        "Stop Loss — the price at which to exit and cut your loss before it grows larger.",
  "Stop Loss":   "Stop Loss — the price at which to exit and cut your loss before it grows larger.",
  "Target":      "Price target — the level where the analysis suggests considering taking profits.",
  "R/R":         "Risk/Reward — potential gain vs. potential loss. A 1:3 ratio means risking $1 to potentially make $3.",
  "Risk/Reward": "Risk/Reward — potential gain vs. potential loss. A 1:3 ratio means risking $1 to potentially make $3.",
  "Confidence":  "AI confidence score (1–10) based on the quality and alignment of available data and signals.",
};

interface Props {
  term: string;
}

export function MetricTooltip({ term }: Props) {
  const [open, setOpen] = useState(false);
  const [style, setStyle] = useState<React.CSSProperties>({});
  const btnRef = useRef<HTMLButtonElement>(null);
  const def = DEFS[term];

  useEffect(() => {
    if (!open) return;
    const close = (e: MouseEvent | TouchEvent) => {
      if (btnRef.current && !btnRef.current.contains(e.target as Node)) setOpen(false);
    };
    document.addEventListener("mousedown", close);
    document.addEventListener("touchstart", close);
    return () => {
      document.removeEventListener("mousedown", close);
      document.removeEventListener("touchstart", close);
    };
  }, [open]);

  if (!def) return null;

  const handleToggle = (e: React.MouseEvent) => {
    e.stopPropagation();
    if (!open && btnRef.current) {
      const r = btnRef.current.getBoundingClientRect();
      const tipW = 220;
      const left = Math.max(8, Math.min(r.left + r.width / 2 - tipW / 2, window.innerWidth - tipW - 8));
      const above = r.top > 150;
      setStyle(
        above
          ? { position: "fixed", left, bottom: window.innerHeight - r.top + 8, zIndex: 9999, width: tipW }
          : { position: "fixed", left, top: r.bottom + 8, zIndex: 9999, width: tipW }
      );
    }
    setOpen(v => !v);
  };

  return (
    <>
      <button
        ref={btnRef}
        onClick={handleToggle}
        className="inline-flex items-center justify-center text-zinc-600 hover:text-cyan-500 active:text-cyan-400 transition-colors ml-0.5 shrink-0 touch-manipulation min-w-[16px] min-h-[16px]"
        aria-label={`What is ${term}?`}
      >
        <Info size={9} />
      </button>
      {open && (
        <span
          style={style}
          className="bg-zinc-800 border border-zinc-700/80 rounded-xl px-3 py-2.5 text-[11px] text-zinc-300 leading-relaxed shadow-2xl pointer-events-none"
        >
          <span className="font-semibold text-zinc-100 block mb-1">{term}</span>
          {def}
        </span>
      )}
    </>
  );
}
