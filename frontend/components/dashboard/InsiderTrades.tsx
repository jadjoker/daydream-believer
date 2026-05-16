"use client";
import { useData } from "@/hooks/useData";
import { api } from "@/lib/api";
import { formatNum, formatMarketCap, colorClass } from "@/lib/utils";
import { Card } from "@/components/ui/Card";
import { Badge } from "@/components/ui/Badge";
import { ExternalLink } from "lucide-react";

interface InsiderTradesProps {
  ticker: string;
}

export default function InsiderTrades({ ticker }: InsiderTradesProps) {
  const { data, loading } = useData(
    () => api.insiderTrades(ticker) as Promise<any>,
    [ticker],
    { refreshInterval: 3600000 }
  );

  const { data: filings, loading: loadingFilings } = useData(
    () => api.secFilings(ticker, "8-K") as Promise<any>,
    [ticker],
    { refreshInterval: 3600000 }
  );

  const trades = data?.trades || [];
  const recentFilings = filings?.filings || [];

  return (
    <Card title="Insider Trades & SEC Filings">
      <div className="space-y-4">
        {/* Insider trades */}
        <div>
          <div className="text-xs text-zinc-500 uppercase tracking-wider mb-2">Insider Transactions (Form 4)</div>
          {loading ? (
            <div className="space-y-2 animate-pulse">
              {Array.from({ length: 4 }).map((_, i) => <div key={i} className="h-10 bg-zinc-800 rounded" />)}
            </div>
          ) : trades.length === 0 ? (
            <div className="text-zinc-600 text-sm py-2">No recent insider transactions found</div>
          ) : (
            <div className="overflow-auto max-h-48">
              <table className="data-table text-xs">
                <thead>
                  <tr>
                    <th>Insider</th>
                    <th>Title</th>
                    <th>Type</th>
                    <th>Shares</th>
                    <th>Price</th>
                    <th>Value</th>
                    <th>Date</th>
                  </tr>
                </thead>
                <tbody>
                  {trades.slice(0, 15).map((t: any, i: number) => {
                    const isBuy = t.trade_type?.toLowerCase().includes("p") || t.trade_type?.toLowerCase().includes("buy") || t.trade_type?.toLowerCase().includes("acqui");
                    return (
                      <tr key={i}>
                        <td className="font-medium text-zinc-200 max-w-[100px] truncate">{t.insider_name || "—"}</td>
                        <td className="text-zinc-500 max-w-[80px] truncate">{t.insider_title || "—"}</td>
                        <td>
                          <Badge variant={isBuy ? "bullish" : "bearish"} className="text-[10px]">
                            {t.trade_type || "Unknown"}
                          </Badge>
                        </td>
                        <td className="tabular-nums">{t.shares > 0 ? formatNum(t.shares, 0) : "—"}</td>
                        <td className="tabular-nums">{t.price > 0 ? `$${formatNum(t.price, 2)}` : "—"}</td>
                        <td className={`tabular-nums ${isBuy ? "text-emerald-400" : "text-red-400"}`}>
                          {t.value > 0 ? formatMarketCap(t.value) : "—"}
                        </td>
                        <td className="text-zinc-500">{t.trade_date?.slice(0, 10) || t.filed_date?.slice(0, 10) || "—"}</td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          )}
        </div>

        {/* Recent SEC filings */}
        <div>
          <div className="text-xs text-zinc-500 uppercase tracking-wider mb-2">Recent 8-K Filings</div>
          {loadingFilings ? (
            <div className="space-y-2 animate-pulse">
              {Array.from({ length: 3 }).map((_, i) => <div key={i} className="h-8 bg-zinc-800 rounded" />)}
            </div>
          ) : recentFilings.length === 0 ? (
            <div className="text-zinc-600 text-sm py-2">No recent 8-K filings</div>
          ) : (
            <div className="space-y-1.5">
              {recentFilings.slice(0, 5).map((f: any, i: number) => (
                <div key={i} className="flex items-center justify-between bg-zinc-800/40 rounded-lg px-3 py-2">
                  <div>
                    <span className="text-xs font-medium text-cyan-400 mr-2">{f.form}</span>
                    <span className="text-xs text-zinc-400">{f.description}</span>
                  </div>
                  <div className="flex items-center gap-2">
                    <span className="text-xs text-zinc-500">{f.date}</span>
                    {f.url && (
                      <a href={f.url} target="_blank" rel="noopener noreferrer" className="text-zinc-500 hover:text-zinc-300">
                        <ExternalLink size={11} />
                      </a>
                    )}
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
      </div>
    </Card>
  );
}
