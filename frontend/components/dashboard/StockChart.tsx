"use client";
import { useEffect, useRef, useState } from "react";
import { useData } from "@/hooks/useData";
import { api } from "@/lib/api";
import { formatPrice, colorClass } from "@/lib/utils";

const PERIODS = [
  { label: "1D",  period: "1d",  interval: "5m"  },
  { label: "5D",  period: "5d",  interval: "15m" },
  { label: "1M",  period: "1mo", interval: "1d"  },
  { label: "3M",  period: "3mo", interval: "1d"  },
  { label: "6M",  period: "6mo", interval: "1d"  },
  { label: "1Y",  period: "1y",  interval: "1d"  },
  { label: "2Y",  period: "2y",  interval: "1wk" },
  { label: "5Y",  period: "5y",  interval: "1wk" },
];

function calcSMA(bars: any[], n: number) {
  const out: { time: number; value: number }[] = [];
  for (let i = n - 1; i < bars.length; i++) {
    let sum = 0;
    for (let j = i - n + 1; j <= i; j++) sum += bars[j].close;
    out.push({ time: Math.floor(new Date(bars[i].timestamp).getTime() / 1000), value: +(sum / n).toFixed(4) });
  }
  return out;
}

interface StockChartProps {
  ticker: string;
  price?: number;
  changePct?: number;
}

export default function StockChart({ ticker, price, changePct }: StockChartProps) {
  const chartRef        = useRef<HTMLDivElement>(null);
  const chartInst       = useRef<any>(null);
  const mainSeriesRef   = useRef<any>(null);
  const volumeSeriesRef = useRef<any>(null);
  const ma20Ref         = useRef<any>(null);
  const ma50Ref         = useRef<any>(null);
  const ma200Ref        = useRef<any>(null);
  const hoveredRef      = useRef<any>(null);

  const [selectedPeriod, setSelectedPeriod] = useState(PERIODS[3]); // 3M default
  const [chartType, setChartType]           = useState<"candle" | "line">("candle");
  const [showMA20, setShowMA20]             = useState(true);
  const [showMA50, setShowMA50]             = useState(true);
  const [showMA200, setShowMA200]           = useState(false);
  const [hovered, setHovered]               = useState<any>(null);

  const { data, loading } = useData(
    () => api.ohlcv(ticker, selectedPeriod.period, selectedPeriod.interval) as Promise<any>,
    [ticker, selectedPeriod.period],
    { refreshInterval: 60000 },
  );

  // Initialize chart (runs once per mount)
  useEffect(() => {
    if (!chartRef.current) return;
    let destroyed = false;
    let observer: ResizeObserver | null = null;

    import("lightweight-charts").then(({
      createChart, ColorType, CrosshairMode, CandlestickSeries, HistogramSeries, LineSeries,
    }) => {
      if (destroyed || !chartRef.current) return;

      const chart = createChart(chartRef.current, {
        width:  chartRef.current.clientWidth,
        height: 340,
        layout: {
          background: { type: ColorType.Solid, color: "#0c0c0e" },
          textColor: "#71717a",
          fontSize: 11,
        },
        grid: {
          vertLines: { color: "#1c1c1f" },
          horzLines: { color: "#1c1c1f" },
        },
        crosshair: { mode: CrosshairMode.Normal },
        rightPriceScale: { borderColor: "#27272a", textColor: "#71717a" },
        timeScale:       { borderColor: "#27272a", timeVisible: true, secondsVisible: false },
      });

      // Volume (bottom 18% overlay)
      const volumeSeries = chart.addSeries(HistogramSeries, {
        priceFormat:  { type: "volume" },
        priceScaleId: "volume",
      });
      chart.priceScale("volume").applyOptions({ scaleMargins: { top: 0.82, bottom: 0 } });

      // Main price series
      let mainSeries: any;
      if (chartType === "candle") {
        mainSeries = chart.addSeries(CandlestickSeries, {
          upColor:        "#34d399",
          downColor:      "#f87171",
          borderUpColor:  "#34d399",
          borderDownColor:"#f87171",
          wickUpColor:    "#34d399",
          wickDownColor:  "#f87171",
        });
      } else {
        mainSeries = chart.addSeries(LineSeries, {
          color:             "#22d3ee",
          lineWidth:         2,
          priceLineVisible:  false,
        });
      }

      // MA series
      const addMALine = (color: string) => chart.addSeries(LineSeries, {
        color,
        lineWidth:            1,
        priceLineVisible:     false,
        lastValueVisible:     false,
        crosshairMarkerVisible: false,
      });

      const ma20Series  = showMA20  ? addMALine("#fbbf24") : null;
      const ma50Series  = showMA50  ? addMALine("#a78bfa") : null;
      const ma200Series = showMA200 ? addMALine("#f87171") : null;

      chartInst.current       = chart;
      mainSeriesRef.current   = mainSeries;
      volumeSeriesRef.current = volumeSeries;
      ma20Ref.current         = ma20Series;
      ma50Ref.current         = ma50Series;
      ma200Ref.current        = ma200Series;

      // OHLC hover tooltip
      chart.subscribeCrosshairMove((param: any) => {
        if (!param.time) { hoveredRef.current = null; setHovered(null); return; }
        const d = param.seriesData.get(mainSeries);
        hoveredRef.current = d ?? null;
        setHovered(d ?? null);
      });

      observer = new ResizeObserver(() => {
        if (chartRef.current && !destroyed) {
          chart.applyOptions({ width: chartRef.current.clientWidth });
        }
      });
      observer.observe(chartRef.current);
    });

    return () => {
      destroyed = true;
      observer?.disconnect();
      if (chartInst.current) {
        chartInst.current.remove();
        chartInst.current       = null;
        mainSeriesRef.current   = null;
        volumeSeriesRef.current = null;
        ma20Ref.current         = null;
        ma50Ref.current         = null;
        ma200Ref.current        = null;
      }
    };
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [chartType, showMA20, showMA50, showMA200]);

  // Update data whenever it loads
  useEffect(() => {
    if (!data?.bars || !mainSeriesRef.current || !volumeSeriesRef.current) return;

    const bars = data.bars;
    const volumes = bars.map((b: any) => ({
      time:  Math.floor(new Date(b.timestamp).getTime() / 1000),
      value: b.volume,
      color: b.close >= b.open ? "rgba(52,211,153,0.35)" : "rgba(248,113,113,0.35)",
    }));

    if (chartType === "candle") {
      mainSeriesRef.current.setData(bars.map((b: any) => ({
        time:  Math.floor(new Date(b.timestamp).getTime() / 1000),
        open:  b.open,
        high:  b.high,
        low:   b.low,
        close: b.close,
      })));
    } else {
      mainSeriesRef.current.setData(bars.map((b: any) => ({
        time:  Math.floor(new Date(b.timestamp).getTime() / 1000),
        value: b.close,
      })));
    }

    volumeSeriesRef.current.setData(volumes);

    if (ma20Ref.current)  ma20Ref.current.setData(calcSMA(bars, 20));
    if (ma50Ref.current)  ma50Ref.current.setData(calcSMA(bars, 50));
    if (ma200Ref.current) ma200Ref.current.setData(calcSMA(bars, 200));

    chartInst.current?.timeScale().fitContent();
  }, [data, chartType]);

  const last = data?.bars?.[data.bars.length - 1];
  const display = hovered ?? (last ? { open: last.open, high: last.high, low: last.low, close: last.close } : null);
  const isUp = display
    ? ((display.close ?? display.value ?? 0) >= (display.open ?? display.close ?? 0))
    : (changePct ?? 0) >= 0;

  return (
    <div className="bg-zinc-900 border border-zinc-800 rounded-xl overflow-hidden">
      {/* Header bar */}
      <div className="flex flex-wrap items-center justify-between gap-2 px-4 py-3 border-b border-zinc-800">
        <div className="flex items-center gap-3">
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

        {/* Period selector */}
        <div className="flex gap-0.5 bg-zinc-950/60 border border-zinc-800 rounded-lg p-0.5">
          {PERIODS.map((p) => (
            <button
              key={p.label}
              onClick={() => setSelectedPeriod(p)}
              className={`text-xs px-2 py-1 rounded transition-colors ${
                selectedPeriod.label === p.label
                  ? "bg-zinc-700 text-zinc-100"
                  : "text-zinc-500 hover:text-zinc-300"
              }`}
            >
              {p.label}
            </button>
          ))}
        </div>
      </div>

      {/* Sub-controls: chart type + MAs */}
      <div className="flex flex-wrap items-center justify-between gap-2 px-4 py-2 border-b border-zinc-800/60">
        {/* OHLC hover info */}
        <div className="flex gap-2 text-xs font-mono min-w-0">
          {display?.open != null ? (
            <span className={isUp ? "text-emerald-400" : "text-red-400"}>
              <span className="text-zinc-500">O </span>{formatPrice(display.open)}&nbsp;
              <span className="text-zinc-500">H </span>{formatPrice(display.high)}&nbsp;
              <span className="text-zinc-500">L </span>{formatPrice(display.low)}&nbsp;
              <span className="text-zinc-500">C </span>{formatPrice(display.close)}
            </span>
          ) : display?.value != null ? (
            <span className={isUp ? "text-emerald-400" : "text-red-400"}>
              {formatPrice(display.value)}
            </span>
          ) : (
            <span className="text-zinc-600">Hover for OHLC</span>
          )}
        </div>

        <div className="flex items-center gap-2 shrink-0">
          {/* Chart type toggle */}
          <div className="flex gap-0.5 bg-zinc-950/60 border border-zinc-800 rounded-lg p-0.5">
            {(["candle", "line"] as const).map((t) => (
              <button
                key={t}
                onClick={() => setChartType(t)}
                className={`text-xs px-2 py-1 rounded transition-colors ${
                  chartType === t ? "bg-zinc-700 text-zinc-100" : "text-zinc-500 hover:text-zinc-300"
                }`}
              >
                {t === "candle" ? "Candles" : "Line"}
              </button>
            ))}
          </div>

          {/* MA toggles */}
          <div className="flex gap-1">
            {[
              { n: "20",  active: showMA20,  cls: "text-amber-400 border-amber-700/50",  toggle: () => setShowMA20((v) => !v) },
              { n: "50",  active: showMA50,  cls: "text-violet-400 border-violet-700/50", toggle: () => setShowMA50((v) => !v) },
              { n: "200", active: showMA200, cls: "text-red-400 border-red-700/50",       toggle: () => setShowMA200((v) => !v) },
            ].map(({ n, active, cls, toggle }) => (
              <button
                key={n}
                onClick={toggle}
                title={`SMA ${n}`}
                className={`text-[10px] px-1.5 py-0.5 rounded border font-semibold transition-opacity ${
                  active ? `${cls} opacity-100` : "text-zinc-600 border-zinc-700/40 opacity-40"
                }`}
              >
                {n}
              </button>
            ))}
          </div>
        </div>
      </div>

      {/* Chart */}
      <div className="relative" style={{ background: "#0c0c0e" }}>
        {loading && (
          <div className="absolute inset-0 flex items-center justify-center bg-zinc-950/60 z-10">
            <div className="w-5 h-5 border-2 border-cyan-500 border-t-transparent rounded-full animate-spin" />
          </div>
        )}
        <div ref={chartRef} style={{ height: 340 }} />
      </div>

      {/* Legend */}
      {(showMA20 || showMA50 || showMA200) && (
        <div className="flex gap-3 px-4 py-1.5 border-t border-zinc-800/60 text-[10px]">
          {showMA20  && <span className="text-amber-400/80">— SMA 20</span>}
          {showMA50  && <span className="text-violet-400/80">— SMA 50</span>}
          {showMA200 && <span className="text-red-400/80">— SMA 200</span>}
        </div>
      )}
    </div>
  );
}
