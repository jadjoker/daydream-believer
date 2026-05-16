"use client";
import { useData } from "@/hooks/useData";
import { api } from "@/lib/api";
import { formatNum, formatPrice, colorClass } from "@/lib/utils";
import { Card, StatCard } from "@/components/ui/Card";
import { Badge } from "@/components/ui/Badge";
import { Zap } from "lucide-react";

interface OptionsFlowProps {
  ticker: string;
}

export default function OptionsFlow({ ticker }: OptionsFlowProps) {
  const { data, loading } = useData(
    () => api.optionsFlow(ticker) as Promise<any>,
    [ticker],
    { refreshInterval: 180000 }
  );

  if (loading) return <LoadingSkeleton />;
  if (!data) return <div className="text-zinc-500 text-sm p-4">No options data</div>;

  const pcrVariant = data.put_call_ratio > 1.2
    ? "bearish"
    : data.put_call_ratio < 0.8
    ? "bullish"
    : "neutral";

  const totalVolume = (data.total_call_volume || 0) + (data.total_put_volume || 0);
  const callPct = totalVolume > 0 ? (data.total_call_volume / totalVolume) * 100 : 50;
  const putPct = 100 - callPct;

  return (
    <Card
      title="Options Flow"
      titleRight={
        <Badge variant={pcrVariant}>P/C: {formatNum(data.put_call_ratio, 2)}</Badge>
      }
    >
      <div className="space-y-4">
        {/* Key stats */}
        <div className="grid grid-cols-3 gap-2">
          <StatCard
            label="P/C Ratio"
            value={formatNum(data.put_call_ratio, 2)}
            valueClass={data.put_call_ratio > 1.2 ? "text-red-400" : data.put_call_ratio < 0.8 ? "text-emerald-400" : "text-yellow-400"}
            sub={data.put_call_ratio > 1 ? "Bearish pressure" : "Bullish pressure"}
          />
          <StatCard
            label="Max Pain"
            value={data.max_pain ? formatPrice(data.max_pain) : "—"}
            valueClass="text-zinc-300"
            sub="Options max pain strike"
          />
          <StatCard
            label="IV Rank"
            value={data.iv_rank != null ? `${data.iv_rank.toFixed(0)}%` : "—"}
            valueClass={data.iv_rank > 70 ? "text-red-400" : data.iv_rank < 30 ? "text-emerald-400" : "text-yellow-400"}
          />
        </div>

        {/* Volume breakdown */}
        <div>
          <div className="flex justify-between text-xs text-zinc-500 mb-1">
            <span className="text-emerald-500">Calls {formatNum(data.total_call_volume)} vol / {formatNum(data.total_call_oi)} OI</span>
            <span className="text-red-500">Puts {formatNum(data.total_put_volume)} vol / {formatNum(data.total_put_oi)} OI</span>
          </div>
          <div className="h-2 bg-zinc-800 rounded-full overflow-hidden flex">
            <div className="h-full bg-emerald-500/70" style={{ width: `${callPct}%` }} />
            <div className="h-full bg-red-500/70" style={{ width: `${putPct}%` }} />
          </div>
          <div className="flex justify-between text-xs mt-1 text-zinc-500">
            <span>{callPct.toFixed(1)}% Calls</span>
            <span>{putPct.toFixed(1)}% Puts</span>
          </div>
        </div>

        {/* Unusual activity */}
        {data.unusual_contracts?.length > 0 && (
          <div>
            <div className="flex items-center gap-1.5 text-xs text-zinc-500 uppercase tracking-wider mb-2">
              <Zap size={10} className="text-yellow-500" />
              Unusual Activity ({data.unusual_contracts.length})
            </div>
            <div className="overflow-auto max-h-52">
              <table className="data-table text-xs">
                <thead>
                  <tr>
                    <th>Type</th>
                    <th>Strike</th>
                    <th>Expiry</th>
                    <th>Vol</th>
                    <th>OI</th>
                    <th>V/OI</th>
                    <th>IV%</th>
                    <th>Last</th>
                  </tr>
                </thead>
                <tbody>
                  {data.unusual_contracts.slice(0, 15).map((c: any, i: number) => (
                    <tr key={i}>
                      <td>
                        <span className={`font-medium ${c.option_type === "call" ? "text-emerald-400" : "text-red-400"}`}>
                          {c.option_type.toUpperCase()}
                        </span>
                      </td>
                      <td className="tabular-nums">${formatNum(c.strike, 2)}</td>
                      <td className="text-zinc-400">{c.expiry}</td>
                      <td className="tabular-nums text-cyan-400">{formatNum(c.volume)}</td>
                      <td className="tabular-nums text-zinc-400">{formatNum(c.open_interest)}</td>
                      <td className={`tabular-nums font-medium ${c.vol_oi_ratio > 3 ? "text-yellow-400" : "text-zinc-400"}`}>
                        {formatNum(c.vol_oi_ratio, 1)}x
                      </td>
                      <td className="tabular-nums text-zinc-400">{formatNum(c.implied_volatility, 1)}%</td>
                      <td className="tabular-nums">${formatNum(c.last_price, 2)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        )}
      </div>
    </Card>
  );
}

function LoadingSkeleton() {
  return (
    <div className="bg-zinc-900 border border-zinc-800 rounded-xl p-4 space-y-3 animate-pulse">
      <div className="h-4 bg-zinc-800 rounded w-32" />
      <div className="grid grid-cols-3 gap-2">
        {Array.from({ length: 3 }).map((_, i) => <div key={i} className="h-16 bg-zinc-800 rounded-lg" />)}
      </div>
      <div className="h-24 bg-zinc-800 rounded" />
    </div>
  );
}
