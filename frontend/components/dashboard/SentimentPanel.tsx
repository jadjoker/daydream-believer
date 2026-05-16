"use client";
import { useData } from "@/hooks/useData";
import { api } from "@/lib/api";
import { sentimentColor, sentimentBg } from "@/lib/utils";
import { Card } from "@/components/ui/Card";
import { Badge } from "@/components/ui/Badge";
import { MessageSquare, TrendingUp, TrendingDown } from "lucide-react";

interface SentimentPanelProps {
  ticker: string;
}

export default function SentimentPanel({ ticker }: SentimentPanelProps) {
  const { data, loading } = useData(
    () => api.sentiment(ticker) as Promise<any>,
    [ticker],
    { refreshInterval: 300000 }
  );

  if (loading) return <LoadingSkeleton />;
  if (!data) return <div className="text-zinc-500 text-sm p-4">No sentiment data</div>;

  const sources = [
    { key: "reddit", label: "Reddit", icon: "📱", data: data.reddit },
    { key: "stocktwits", label: "Stocktwits", icon: "💬", data: data.stocktwits },
    { key: "news", label: "News", icon: "📰", data: data.news },
  ];

  const compositeVariant = data.composite_label?.toLowerCase() === "bullish"
    ? "bullish"
    : data.composite_label?.toLowerCase() === "bearish"
    ? "bearish"
    : "neutral";

  return (
    <Card
      title="Sentiment Analysis"
      titleRight={<Badge variant={compositeVariant}>{data.composite_label}</Badge>}
    >
      <div className="space-y-4">
        {/* Composite score */}
        <div className="flex items-center gap-3 p-3 bg-zinc-800/50 rounded-lg">
          <div className="flex-1">
            <div className="text-xs text-zinc-500 mb-1">Composite Score</div>
            <div className={`text-2xl font-bold tabular-nums ${sentimentColor(data.composite_label)}`}>
              {data.composite_score >= 0 ? "+" : ""}{(data.composite_score * 100).toFixed(1)}
            </div>
          </div>
          <CompositeGauge score={data.composite_score} />
        </div>

        {/* Per-source breakdown */}
        <div className="space-y-3">
          {sources.map(({ key, label, icon, data: src }) => {
            if (!src) return (
              <div key={key} className="flex items-center gap-2 text-zinc-600 text-sm">
                <span>{icon}</span>
                <span>{label}</span>
                <span className="text-xs">— not configured</span>
              </div>
            );
            const variant = src.label?.toLowerCase() === "bullish" ? "bullish" : src.label?.toLowerCase() === "bearish" ? "bearish" : "neutral";
            const total = src.mention_count || 1;
            const bullPct = Math.round((src.bullish_count / total) * 100);
            const bearPct = Math.round((src.bearish_count / total) * 100);
            return (
              <div key={key} className="space-y-1.5">
                <div className="flex items-center justify-between">
                  <div className="flex items-center gap-2">
                    <span className="text-base">{icon}</span>
                    <span className="text-sm font-medium">{label}</span>
                    <span className="text-xs text-zinc-500">{src.mention_count} mentions</span>
                  </div>
                  <Badge variant={variant}>{src.label}</Badge>
                </div>
                {/* Bull/Bear bar */}
                <div className="h-1.5 bg-zinc-800 rounded-full overflow-hidden flex">
                  <div className="h-full bg-emerald-500/70 transition-all" style={{ width: `${bullPct}%` }} />
                  <div className="h-full bg-zinc-700" style={{ width: `${100 - bullPct - bearPct}%` }} />
                  <div className="h-full bg-red-500/70 transition-all" style={{ width: `${bearPct}%` }} />
                </div>
                <div className="flex justify-between text-xs text-zinc-500">
                  <span className="text-emerald-500/80">{bullPct}% Bull</span>
                  <span className="text-red-500/80">{bearPct}% Bear</span>
                </div>
              </div>
            );
          })}
        </div>

        {/* Top posts */}
        {data.top_posts?.length > 0 && (
          <div>
            <div className="text-xs text-zinc-500 uppercase tracking-wider mb-2">Top Mentions</div>
            <div className="space-y-2">
              {data.top_posts.slice(0, 4).map((post: any, i: number) => (
                <div key={i} className="bg-zinc-800/40 rounded-lg p-2.5 text-xs">
                  <div className="text-zinc-300 line-clamp-2 leading-relaxed">
                    {post.title || post.text || "No content"}
                  </div>
                  <div className="flex items-center gap-2 mt-1 text-zinc-600">
                    <span>{post.subreddit ? `r/${post.subreddit}` : post.source || ""}</span>
                    {post.score && <span>↑ {post.score}</span>}
                  </div>
                </div>
              ))}
            </div>
          </div>
        )}
      </div>
    </Card>
  );
}

function CompositeGauge({ score }: { score: number }) {
  const clamped = Math.max(-1, Math.min(1, score));
  const pct = ((clamped + 1) / 2) * 100;
  const color = score > 0.1 ? "#34d399" : score < -0.1 ? "#f87171" : "#facc15";
  return (
    <div className="flex flex-col items-center gap-1">
      <svg width={64} height={36} viewBox="0 0 64 36">
        <path d="M8 32 A24 24 0 0 1 56 32" fill="none" stroke="#27272a" strokeWidth={6} strokeLinecap="round" />
        <path
          d="M8 32 A24 24 0 0 1 56 32"
          fill="none"
          stroke={color}
          strokeWidth={6}
          strokeLinecap="round"
          strokeDasharray={`${pct * 0.754} 100`}
        />
      </svg>
    </div>
  );
}

function LoadingSkeleton() {
  return (
    <div className="bg-zinc-900 border border-zinc-800 rounded-xl p-4 space-y-3 animate-pulse">
      <div className="h-4 bg-zinc-800 rounded w-32" />
      <div className="h-16 bg-zinc-800 rounded-lg" />
      {Array.from({ length: 3 }).map((_, i) => <div key={i} className="h-12 bg-zinc-800 rounded" />)}
    </div>
  );
}
