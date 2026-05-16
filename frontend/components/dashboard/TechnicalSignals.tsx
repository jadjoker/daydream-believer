"use client";
import { useData } from "@/hooks/useData";
import { api } from "@/lib/api";
import { formatNum, formatPct, rsiColor, colorClass } from "@/lib/utils";
import { Card, StatCard } from "@/components/ui/Card";
import { Badge } from "@/components/ui/Badge";
import { TrendingUp, TrendingDown, Minus } from "lucide-react";

interface TechnicalSignalsProps {
  ticker: string;
}

export default function TechnicalSignals({ ticker }: TechnicalSignalsProps) {
  const { data, loading } = useData(
    () => api.technicals(ticker) as Promise<any>,
    [ticker],
    { refreshInterval: 120000 }
  );

  if (loading) return <LoadingSkeleton />;
  if (!data) return <div className="text-zinc-500 text-sm p-4">No technical data</div>;

  const summaryVariant = data.signal_summary.includes("BULL")
    ? "bullish"
    : data.signal_summary.includes("BEAR")
    ? "bearish"
    : "neutral";

  return (
    <Card
      title="Technical Analysis"
      titleRight={
        <Badge variant={summaryVariant}>{data.signal_summary}</Badge>
      }
    >
      <div className="space-y-4">
        {/* Key indicators grid */}
        <div className="grid grid-cols-4 gap-2">
          <StatCard
            label="RSI (14)"
            value={formatNum(data.rsi_14, 1)}
            valueClass={rsiColor(data.rsi_14)}
            sub={data.rsi_14 >= 70 ? "Overbought" : data.rsi_14 <= 30 ? "Oversold" : "Neutral"}
          />
          <StatCard
            label="MACD Hist"
            value={formatNum(data.macd_hist, 3)}
            valueClass={colorClass(data.macd_hist)}
            sub={`Signal: ${formatNum(data.macd_signal, 3)}`}
          />
          <StatCard
            label="BB %"
            value={data.bb_pct != null ? `${(data.bb_pct * 100).toFixed(1)}%` : "—"}
            valueClass={data.bb_pct > 0.8 ? "text-red-400" : data.bb_pct < 0.2 ? "text-emerald-400" : "text-zinc-300"}
            sub={`Upper: ${formatNum(data.bb_upper, 2)}`}
          />
          <StatCard
            label="Rel. Volume"
            value={formatNum(data.rel_volume, 2) + "x"}
            valueClass={data.rel_volume > 2 ? "text-cyan-400" : "text-zinc-300"}
            sub={`ATR: ${formatNum(data.atr_14, 2)}`}
          />
        </div>

        {/* Moving averages */}
        <div>
          <div className="text-xs text-zinc-500 mb-2 uppercase tracking-wider">Moving Averages</div>
          <div className="grid grid-cols-4 gap-2">
            {[
              { label: "EMA 9", val: data.ema_9, price: data.price },
              { label: "EMA 21", val: data.ema_21, price: data.price },
              { label: "EMA 50", val: data.ema_50, price: data.price },
              { label: "SMA 200", val: data.sma_200, price: data.price },
            ].map(({ label, val, price }) => (
              <div key={label} className="bg-zinc-800/50 rounded-lg p-2">
                <div className="text-xs text-zinc-500">{label}</div>
                <div className={`text-sm font-medium tabular-nums ${val != null ? (price > val ? "text-emerald-400" : "text-red-400") : "text-zinc-500"}`}>
                  {formatNum(val, 2)}
                </div>
              </div>
            ))}
          </div>
        </div>

        {/* Oscillators */}
        <div>
          <div className="text-xs text-zinc-500 mb-2 uppercase tracking-wider">Oscillators</div>
          <div className="grid grid-cols-4 gap-2">
            <StatCard label="Stoch %K" value={formatNum(data.stoch_k, 1)} valueClass={data.stoch_k > 80 ? "text-red-400" : data.stoch_k < 20 ? "text-emerald-400" : "text-zinc-300"} />
            <StatCard label="Stoch %D" value={formatNum(data.stoch_d, 1)} valueClass="text-zinc-300" />
            <StatCard label="ADX" value={formatNum(data.adx, 1)} valueClass={data.adx > 25 ? "text-cyan-400" : "text-zinc-300"} sub={data.adx > 25 ? "Trending" : "Ranging"} />
            <StatCard label="CCI" value={formatNum(data.cci, 0)} valueClass={data.cci > 100 ? "text-red-400" : data.cci < -100 ? "text-emerald-400" : "text-zinc-300"} />
          </div>
        </div>

        {/* VWAP + OBV */}
        <div className="grid grid-cols-2 gap-2">
          <StatCard
            label="VWAP"
            value={formatNum(data.vwap, 2)}
            valueClass={data.price > data.vwap ? "text-emerald-400" : "text-red-400"}
            sub={data.price > data.vwap ? "Price above VWAP" : "Price below VWAP"}
          />
          <StatCard label="OBV" value={data.obv != null ? (data.obv / 1e6).toFixed(2) + "M" : "—"} valueClass="text-zinc-300" />
        </div>

        {/* Signals */}
        {(data.bull_signals?.length > 0 || data.bear_signals?.length > 0) && (
          <div className="grid grid-cols-2 gap-3">
            {data.bull_signals?.length > 0 && (
              <div>
                <div className="text-xs text-emerald-500 mb-1.5 uppercase tracking-wider flex items-center gap-1">
                  <TrendingUp size={11} /> Bullish Signals
                </div>
                <div className="space-y-1">
                  {data.bull_signals.map((s: string, i: number) => (
                    <div key={i} className="text-xs text-emerald-300/80 bg-emerald-500/10 rounded px-2 py-1">
                      {s}
                    </div>
                  ))}
                </div>
              </div>
            )}
            {data.bear_signals?.length > 0 && (
              <div>
                <div className="text-xs text-red-500 mb-1.5 uppercase tracking-wider flex items-center gap-1">
                  <TrendingDown size={11} /> Bearish Signals
                </div>
                <div className="space-y-1">
                  {data.bear_signals.map((s: string, i: number) => (
                    <div key={i} className="text-xs text-red-300/80 bg-red-500/10 rounded px-2 py-1">
                      {s}
                    </div>
                  ))}
                </div>
              </div>
            )}
          </div>
        )}
      </div>
    </Card>
  );
}

function LoadingSkeleton() {
  return (
    <div className="bg-zinc-900 border border-zinc-800 rounded-xl p-4 space-y-3 animate-pulse">
      <div className="h-4 bg-zinc-800 rounded w-40" />
      <div className="grid grid-cols-4 gap-2">
        {Array.from({ length: 4 }).map((_, i) => <div key={i} className="h-16 bg-zinc-800 rounded-lg" />)}
      </div>
      <div className="grid grid-cols-4 gap-2">
        {Array.from({ length: 4 }).map((_, i) => <div key={i} className="h-12 bg-zinc-800 rounded-lg" />)}
      </div>
    </div>
  );
}
