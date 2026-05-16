"use client";
import { useData } from "@/hooks/useData";
import { api } from "@/lib/api";
import { formatNum, colorClass } from "@/lib/utils";
import { Card } from "@/components/ui/Card";
import { Calendar } from "lucide-react";

export default function EarningsCalendar() {
  const { data, loading } = useData(
    () => api.earningsCalendar(2) as Promise<any>,
    [],
    { refreshInterval: 3600000 }
  );

  const events = data?.events || [];

  // Group by date
  const byDate: Record<string, any[]> = {};
  for (const e of events) {
    if (!e.report_date) continue;
    if (!byDate[e.report_date]) byDate[e.report_date] = [];
    byDate[e.report_date].push(e);
  }
  const sortedDates = Object.keys(byDate).sort();

  return (
    <Card title="Earnings Calendar" titleRight={<span className="text-zinc-500">Next 2 weeks</span>}>
      {loading ? (
        <div className="space-y-3 animate-pulse">
          {Array.from({ length: 4 }).map((_, i) => <div key={i} className="h-20 bg-zinc-800 rounded" />)}
        </div>
      ) : events.length === 0 ? (
        <div className="text-zinc-500 text-sm text-center py-6">
          <Calendar size={24} className="mx-auto mb-2 opacity-30" />
          No earnings data (Finnhub API key required)
        </div>
      ) : (
        <div className="space-y-4 max-h-96 overflow-y-auto pr-1">
          {sortedDates.map((date) => (
            <div key={date}>
              <div className="text-xs font-semibold text-zinc-400 mb-2 sticky top-0 bg-zinc-900 py-1">
                {new Date(date + "T00:00:00").toLocaleDateString("en-US", { weekday: "short", month: "short", day: "numeric" })}
              </div>
              <div className="space-y-1.5">
                {byDate[date].map((e: any, i: number) => (
                  <EarningsRow key={i} event={e} />
                ))}
              </div>
            </div>
          ))}
        </div>
      )}
    </Card>
  );
}

function EarningsRow({ event }: { event: any }) {
  const hasActual = event.eps_actual != null;
  const surprise = event.surprise_pct;
  const timeLabel = event.time === "bmo" ? "BMO" : event.time === "amc" ? "AMC" : event.time || "";

  return (
    <div className="flex items-center justify-between bg-zinc-800/40 rounded-lg px-3 py-2">
      <div className="flex items-center gap-2">
        <span className="font-bold text-cyan-400 text-sm w-14">{event.ticker}</span>
        <span className={`text-xs px-1.5 py-0.5 rounded ${
          timeLabel === "BMO" ? "bg-yellow-500/20 text-yellow-400" :
          timeLabel === "AMC" ? "bg-purple-500/20 text-purple-400" :
          "bg-zinc-700 text-zinc-400"
        }`}>
          {timeLabel || "—"}
        </span>
      </div>
      <div className="flex items-center gap-3 text-xs">
        {event.eps_estimate != null && (
          <div className="text-zinc-500">
            Est: <span className="text-zinc-300">${formatNum(event.eps_estimate, 2)}</span>
          </div>
        )}
        {hasActual && (
          <div>
            Act: <span className={`font-medium ${colorClass(surprise)}`}>${formatNum(event.eps_actual, 2)}</span>
          </div>
        )}
        {surprise != null && (
          <span className={`font-medium ${colorClass(surprise)}`}>
            {surprise > 0 ? "+" : ""}{formatNum(surprise, 1)}%
          </span>
        )}
      </div>
    </div>
  );
}
