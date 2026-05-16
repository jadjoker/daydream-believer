"use client";
import { useData } from "@/hooks/useData";
import { api } from "@/lib/api";
import { formatNum, formatPct, colorClass } from "@/lib/utils";
import { Card } from "@/components/ui/Card";
import { TrendingUp, TrendingDown, Activity } from "lucide-react";

interface IndexTile {
  label: string;
  price: number;
  changePct: number;
}

interface MarketOverviewProps {
  onTickerSelect?: (ticker: string) => void;
}

export default function MarketOverview({ onTickerSelect }: MarketOverviewProps) {
  const { data, loading } = useData(() => api.marketOverview() as Promise<any>, [], {
    refreshInterval: 30000,
  });

  if (loading || !data) {
    return (
      <div className="grid grid-cols-5 gap-3">
        {Array.from({ length: 5 }).map((_, i) => (
          <div key={i} className="bg-zinc-900 border border-zinc-800 rounded-xl h-20 animate-pulse" />
        ))}
      </div>
    );
  }

  const indices: IndexTile[] = [
    { label: "SPY", price: data.spy_price, changePct: data.spy_change_pct },
    { label: "QQQ", price: data.qqq_price, changePct: data.qqq_change_pct },
    { label: "IWM", price: data.iwm_price, changePct: data.iwm_change_pct },
    { label: "DIA", price: data.dia_price, changePct: data.dia_change_pct },
    { label: "VIX", price: data.vix, changePct: data.vix_change_pct },
  ];

  const statusColors: Record<string, string> = {
    open: "bg-emerald-500",
    "pre-market": "bg-yellow-500",
    "after-hours": "bg-orange-500",
    closed: "bg-zinc-500",
  };

  return (
    <div className="space-y-3">
      {/* Market status + index tiles */}
      <div className="flex items-center gap-3 flex-wrap">
        <div className="flex items-center gap-2">
          <span className={`w-2 h-2 rounded-full live-dot ${statusColors[data.market_status] || "bg-zinc-500"}`} />
          <span className="text-xs font-medium text-zinc-400 uppercase tracking-wider">
            {data.market_status}
          </span>
        </div>
      </div>

      <div className="grid grid-cols-5 gap-3">
        {indices.map((idx) => (
          <IndexCard key={idx.label} {...idx} />
        ))}
      </div>

      {/* Sector heatmap */}
      {data.sector_performance?.length > 0 && (
        <div>
          <div className="text-xs text-zinc-500 uppercase tracking-wider mb-2">Sector Performance</div>
          <div className="grid grid-cols-11 gap-1">
            {data.sector_performance.map((s: any) => (
              <SectorTile key={s.name} name={s.name} changePct={s.change_pct} />
            ))}
          </div>
        </div>
      )}

      {/* Trending tickers */}
      {data.trending_tickers?.length > 0 && (
        <div className="flex items-center gap-2 flex-wrap">
          <span className="text-xs text-zinc-500">Trending:</span>
          {data.trending_tickers.map((t: string) => (
            <button
              key={t}
              onClick={() => onTickerSelect?.(t)}
              className="text-xs bg-zinc-800 border border-zinc-700 text-zinc-300 px-2 py-0.5 rounded hover:bg-cyan-800/40 hover:border-cyan-600/40 hover:text-cyan-300 transition-colors"
            >
              {t}
            </button>
          ))}
        </div>
      )}
    </div>
  );
}

function IndexCard({ label, price, changePct }: IndexTile) {
  const up = changePct >= 0;
  return (
    <div className={`bg-zinc-900 border rounded-xl p-3 ${up ? "border-emerald-900/40" : "border-red-900/40"}`}>
      <div className="text-xs font-bold text-zinc-400 mb-1">{label}</div>
      <div className="text-lg font-semibold tabular-nums">{formatNum(price)}</div>
      <div className={`text-sm font-medium tabular-nums flex items-center gap-1 ${colorClass(changePct)}`}>
        {up ? <TrendingUp size={12} /> : <TrendingDown size={12} />}
        {formatPct(changePct)}
      </div>
    </div>
  );
}

function SectorTile({ name, changePct }: { name: string; changePct: number }) {
  const intensity = Math.min(Math.abs(changePct) / 3, 1);
  const bg = changePct > 0
    ? `rgba(52, 211, 153, ${0.1 + intensity * 0.3})`
    : changePct < 0
    ? `rgba(248, 113, 113, ${0.1 + intensity * 0.3})`
    : "rgba(113, 113, 122, 0.15)";
  const shortName = name.replace(" Disc.", "").replace(" Staples", " Stpl").replace("Communication", "Comm");
  return (
    <div
      className="rounded p-1.5 text-center cursor-pointer transition-opacity hover:opacity-80"
      style={{ background: bg }}
      title={`${name}: ${formatPct(changePct)}`}
    >
      <div className="text-[10px] font-medium text-zinc-300 leading-tight truncate">{shortName}</div>
      <div className={`text-[11px] font-semibold tabular-nums ${colorClass(changePct)}`}>
        {formatPct(changePct, 1)}
      </div>
    </div>
  );
}
