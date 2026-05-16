"use client";
import { useEffect, useRef, useState } from "react";
import { useData } from "@/hooks/useData";
import { api } from "@/lib/api";
import { formatPrice, formatPct, colorClass } from "@/lib/utils";

const PERIODS = [
  { label: "1D", period: "1d", interval: "5m" },
  { label: "5D", period: "5d", interval: "15m" },
  { label: "1M", period: "1mo", interval: "1d" },
  { label: "3M", period: "3mo", interval: "1d" },
  { label: "6M", period: "6mo", interval: "1d" },
  { label: "1Y", period: "1y", interval: "1d" },
  { label: "2Y", period: "2y", interval: "1wk" },
];

interface StockChartProps {
  ticker: string;
  price?: number;
  changePct?: number;
}

export default function StockChart({ ticker, price, changePct }: StockChartProps) {
  const chartRef = useRef<HTMLDivElement>(null);
  const chartInstanceRef = useRef<any>(null);
  const candleSeriesRef = useRef<any>(null);
  const volumeSeriesRef = useRef<any>(null);
  const [selectedPeriod, setSelectedPeriod] = useState(PERIODS[3]);

  const { data, loading } = useData(
    () => api.ohlcv(ticker, selectedPeriod.period, selectedPeriod.interval) as Promise<any>,
    [ticker, selectedPeriod.period],
    { refreshInterval: 60000 }
  );

  // Initialize chart
  useEffect(() => {
    if (!chartRef.current) return;
    let destroyed = false;
    let observer: ResizeObserver | null = null;

    import("lightweight-charts").then(({ createChart, ColorType, CrosshairMode, CandlestickSeries, HistogramSeries }) => {
      if (destroyed || !chartRef.current) return;

      const chart = createChart(chartRef.current, {
        width: chartRef.current.clientWidth,
        height: 320,
        layout: {
          background: { type: ColorType.Solid, color: "#0f0f11" },
          textColor: "#71717a",
        },
        grid: {
          vertLines: { color: "#1f1f23" },
          horzLines: { color: "#1f1f23" },
        },
        crosshair: { mode: CrosshairMode.Normal },
        rightPriceScale: {
          borderColor: "#27272a",
          textColor: "#71717a",
        },
        timeScale: {
          borderColor: "#27272a",
          timeVisible: true,
          secondsVisible: false,
        },
      });

      const candleSeries = chart.addSeries(CandlestickSeries, {
        upColor: "#34d399",
        downColor: "#f87171",
        borderUpColor: "#34d399",
        borderDownColor: "#f87171",
        wickUpColor: "#34d399",
        wickDownColor: "#f87171",
      });

      const volumeSeries = chart.addSeries(HistogramSeries, {
        color: "#26a69a",
        priceFormat: { type: "volume" },
        priceScaleId: "volume",
      });
      chart.priceScale("volume").applyOptions({ scaleMargins: { top: 0.85, bottom: 0 } });

      chartInstanceRef.current = chart;
      candleSeriesRef.current = candleSeries;
      volumeSeriesRef.current = volumeSeries;

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
      if (chartInstanceRef.current) {
        chartInstanceRef.current.remove();
        chartInstanceRef.current = null;
        candleSeriesRef.current = null;
        volumeSeriesRef.current = null;
      }
    };
  }, []);

  // Update data
  useEffect(() => {
    if (!data?.bars || !candleSeriesRef.current || !volumeSeriesRef.current) return;
    const candles = data.bars.map((b: any) => ({
      time: Math.floor(new Date(b.timestamp).getTime() / 1000),
      open: b.open,
      high: b.high,
      low: b.low,
      close: b.close,
    }));
    const volumes = data.bars.map((b: any) => ({
      time: Math.floor(new Date(b.timestamp).getTime() / 1000),
      value: b.volume,
      color: b.close >= b.open ? "rgba(52, 211, 153, 0.4)" : "rgba(248, 113, 113, 0.4)",
    }));
    candleSeriesRef.current.setData(candles);
    volumeSeriesRef.current.setData(volumes);
    chartInstanceRef.current?.timeScale().fitContent();
  }, [data]);

  return (
    <div className="bg-zinc-900 border border-zinc-800 rounded-xl overflow-hidden">
      {/* Header */}
      <div className="flex items-center justify-between px-4 py-3 border-b border-zinc-800">
        <div className="flex items-center gap-3">
          <span className="font-bold text-lg">{ticker}</span>
          {price != null && (
            <span className="text-lg font-semibold tabular-nums">{formatPrice(price)}</span>
          )}
          {changePct != null && (
            <span className={`text-sm font-medium tabular-nums ${colorClass(changePct)}`}>
              {formatPct(changePct)}
            </span>
          )}
        </div>
        <div className="flex gap-1">
          {PERIODS.map((p) => (
            <button
              key={p.label}
              onClick={() => setSelectedPeriod(p)}
              className={`text-xs px-2.5 py-1 rounded transition-colors ${
                selectedPeriod.label === p.label
                  ? "bg-cyan-600/30 text-cyan-300 border border-cyan-500/40"
                  : "text-zinc-500 hover:text-zinc-300 hover:bg-zinc-800"
              }`}
            >
              {p.label}
            </button>
          ))}
        </div>
      </div>

      {/* Chart */}
      <div className="relative" style={{ background: "#0f0f11" }}>
        {loading && (
          <div className="absolute inset-0 flex items-center justify-center bg-zinc-950/60 z-10">
            <div className="w-5 h-5 border-2 border-cyan-500 border-t-transparent rounded-full animate-spin" />
          </div>
        )}
        <div ref={chartRef} style={{ height: 320 }} />
      </div>
    </div>
  );
}
