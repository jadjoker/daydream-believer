"use client";
import { useState } from "react";
import { useData } from "@/hooks/useData";
import { api } from "@/lib/api";
import { Card } from "@/components/ui/Card";
import { Badge } from "@/components/ui/Badge";
import { ExternalLink } from "lucide-react";

interface NewsPanelProps {
  ticker?: string;
}

export default function NewsPanel({ ticker }: NewsPanelProps) {
  const [mode, setMode] = useState<"ticker" | "general">(ticker ? "ticker" : "general");

  const { data: tickerNews, loading: loadingTicker } = useData(
    () => ticker ? api.tickerNews(ticker) as Promise<any> : Promise.resolve(null),
    [ticker],
    { refreshInterval: 180000, enabled: !!ticker }
  );

  const { data: generalNews, loading: loadingGeneral } = useData(
    () => api.generalNews() as Promise<any>,
    [],
    { refreshInterval: 300000 }
  );

  const loading = mode === "ticker" ? loadingTicker : loadingGeneral;
  const rawData = mode === "ticker" ? tickerNews : generalNews;
  const articles = rawData?.articles || [];

  return (
    <Card
      title="News Feed"
      titleRight={
        ticker ? (
          <div className="flex gap-1">
            {(["ticker", "general"] as const).map((m) => (
              <button
                key={m}
                onClick={() => setMode(m)}
                className={`text-xs px-2 py-0.5 rounded transition-colors ${
                  mode === m ? "bg-zinc-700 text-zinc-200" : "text-zinc-500 hover:text-zinc-300"
                }`}
              >
                {m === "ticker" ? ticker : "Market"}
              </button>
            ))}
          </div>
        ) : null
      }
    >
      {loading ? (
        <div className="space-y-3">
          {Array.from({ length: 5 }).map((_, i) => (
            <div key={i} className="animate-pulse">
              <div className="h-4 bg-zinc-800 rounded w-3/4 mb-1" />
              <div className="h-3 bg-zinc-800 rounded w-1/2" />
            </div>
          ))}
        </div>
      ) : (
        <div className="space-y-2 max-h-96 overflow-y-auto pr-1">
          {articles.slice(0, 25).map((article: any, i: number) => (
            <NewsItem key={i} article={article} />
          ))}
          {articles.length === 0 && (
            <div className="text-zinc-500 text-sm text-center py-4">No articles found</div>
          )}
        </div>
      )}
    </Card>
  );
}

function NewsItem({ article }: { article: any }) {
  const sentimentVariant = article.sentiment === "positive"
    ? "bullish"
    : article.sentiment === "negative"
    ? "bearish"
    : "neutral";

  const timeAgo = getTimeAgo(article.published_at);

  return (
    <a
      href={article.url}
      target="_blank"
      rel="noopener noreferrer"
      className="block group"
    >
      <div className="bg-zinc-800/40 border border-zinc-800 rounded-lg p-3 hover:border-zinc-700 hover:bg-zinc-800/70 transition-all cursor-pointer">
        <div className="flex items-start justify-between gap-2">
          <div className="flex-1 min-w-0">
            <p className="text-sm text-zinc-200 group-hover:text-white transition-colors line-clamp-2 leading-snug">
              {article.title}
            </p>
            <div className="flex items-center gap-2 mt-1.5 flex-wrap">
              <span className="text-xs text-zinc-500 font-medium">{article.source}</span>
              {timeAgo && <span className="text-xs text-zinc-600">{timeAgo}</span>}
              {article.sentiment && article.sentiment !== "neutral" && (
                <Badge variant={sentimentVariant} className="text-[10px] py-0">
                  {article.sentiment}
                </Badge>
              )}
              {article.tickers?.slice(0, 3).map((t: string) => (
                <span key={t} className="text-[10px] text-cyan-500/70">${t}</span>
              ))}
            </div>
          </div>
          <ExternalLink size={12} className="text-zinc-600 shrink-0 mt-0.5 group-hover:text-zinc-400 transition-colors" />
        </div>
      </div>
    </a>
  );
}

function getTimeAgo(dateStr: string): string {
  try {
    const date = new Date(dateStr);
    const diff = Date.now() - date.getTime();
    const mins = Math.floor(diff / 60000);
    if (mins < 60) return `${mins}m ago`;
    const hrs = Math.floor(mins / 60);
    if (hrs < 24) return `${hrs}h ago`;
    return `${Math.floor(hrs / 24)}d ago`;
  } catch {
    return "";
  }
}
