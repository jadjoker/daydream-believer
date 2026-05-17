"use client";
import { useEffect, useRef } from "react";
import { formatPrice, colorClass } from "@/lib/utils";
import { LineChart } from "lucide-react";

let _counter = 0;

interface StockChartProps {
  ticker: string;
  price?: number;
  changePct?: number;
  height?: number;
}

export default function StockChart({ ticker, price, changePct, height = 520 }: StockChartProps) {
  const containerRef = useRef<HTMLDivElement>(null);
  const idRef = useRef(`tv_${++_counter}`);

  useEffect(() => {
    const id = idRef.current;
    const el = containerRef.current;
    if (!el || !ticker) return;

    // Wipe previous widget content
    el.innerHTML = `<div id="${id}" style="height:100%"></div>`;

    function createWidget() {
      if (typeof (window as any).TradingView === "undefined") return;
      new (window as any).TradingView.widget({
        autosize:            true,
        symbol:              ticker,
        interval:            "W",
        range:               "ALL",
        timezone:            "America/New_York",
        theme:               "dark",
        style:               "2",           // line chart
        locale:              "en",
        toolbar_bg:          "#18181b",
        withdateranges:      true,
        hide_side_toolbar:   true,
        hide_volume:         true,
        allow_symbol_change: false,
        enable_publishing:   false,
        studies:             [],
        container_id:        id,
      });
    }

    // Script is already loaded from a previous mount
    if ((window as any).TradingView) {
      createWidget();
      return;
    }

    // Script is already in the DOM but still loading
    const existing = document.getElementById("_tv_script");
    if (existing) {
      existing.addEventListener("load", createWidget, { once: true });
      return () => existing.removeEventListener("load", createWidget);
    }

    // First load
    const script = document.createElement("script");
    script.id  = "_tv_script";
    script.src = "https://s3.tradingview.com/tv.js";
    script.async = true;
    script.onload = createWidget;
    document.head.appendChild(script);
  }, [ticker]);

  if (!ticker) {
    return (
      <div
        className="bg-zinc-900 border border-zinc-800 rounded-xl flex flex-col items-center justify-center text-zinc-600"
        style={{ height }}
      >
        <LineChart size={32} className="mb-3 opacity-30" />
        <p className="text-sm text-zinc-500">Select a stock to view its chart</p>
        <p className="text-xs text-zinc-600 mt-1">Click any ticker in the AI picks</p>
      </div>
    );
  }

  return (
    <div className="bg-zinc-900 border border-zinc-800 rounded-xl overflow-hidden">
      {(price != null || changePct != null) && (
        <div className="flex items-center gap-3 px-4 py-3 border-b border-zinc-800">
          <span className="font-bold text-base text-zinc-100">{ticker}</span>
          {price != null && (
            <span className="text-base font-semibold tabular-nums">{formatPrice(price)}</span>
          )}
          {changePct != null && (
            <span className={`text-sm font-medium tabular-nums ${colorClass(changePct)}`}>
              {changePct >= 0 ? "+" : ""}{changePct.toFixed(2)}%
            </span>
          )}
        </div>
      )}
      <div ref={containerRef} style={{ height }} />
    </div>
  );
}
