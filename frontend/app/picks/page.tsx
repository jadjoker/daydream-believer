"use client";
import { useState, useEffect, useCallback, useMemo } from "react";
import AIPicks from "@/components/dashboard/AIPicks";
import StockChart from "@/components/dashboard/StockChart";
import StockInfoBar from "@/components/dashboard/StockInfoBar";
import { useData } from "@/hooks/useData";
import { api } from "@/lib/api";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { Lock, TrendingUp, RefreshCw, Clock } from "lucide-react";

function formatAge(dateStr: string): string {
  // Parse "2025-05-23 14:32 ET" — treat as Eastern (approximate UTC-5)
  const m = dateStr.match(/(\d{4}-\d{2}-\d{2}) (\d{2}:\d{2})/);
  if (!m) return dateStr;
  const date = new Date(`${m[1]}T${m[2]}:00-05:00`);
  const secs = Math.floor((Date.now() - date.getTime()) / 1000);
  if (secs < 60) return "just now";
  if (secs < 3600) return `${Math.floor(secs / 60)}m ago`;
  if (secs < 86400) return `${Math.floor(secs / 3600)}h ago`;
  return `${Math.floor(secs / 86400)}d ago`;
}

// ─── Passcode gate ────────────────────────────────────────────────────────────

function PasscodeGate({ onAuth }: { onAuth: () => void }) {
  const [input, setInput] = useState("");
  const [error, setError] = useState("");
  const [checking, setChecking] = useState(false);

  const submit = async (code: string) => {
    if (!code || checking) return;
    setChecking(true);
    setError("");
    try {
      await api.verifyPasscode(code);
      localStorage.setItem("picks_passcode", code);
      onAuth();
    } catch {
      localStorage.removeItem("picks_passcode");
      setError("Incorrect passcode");
    } finally {
      setChecking(false);
    }
  };

  return (
    <div className="min-h-screen bg-zinc-950 flex flex-col items-center justify-center px-4">
      <div className="w-full max-w-sm space-y-6">
        <div className="text-center space-y-2">
          <div className="inline-flex items-center justify-center w-12 h-12 rounded-full bg-zinc-800 border border-zinc-700">
            <Lock size={20} className="text-zinc-400" />
          </div>
          <h1 className="text-lg font-semibold text-zinc-100">AI Picks</h1>
          <p className="text-sm text-zinc-500">Enter passcode to continue</p>
        </div>

        <div className="space-y-3">
          <input
            type="password"
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && submit(input)}
            placeholder="Passcode"
            autoFocus
            className="w-full bg-zinc-900 border border-zinc-700 rounded-lg px-4 py-2.5 text-sm text-zinc-100 placeholder-zinc-600 focus:outline-none focus:border-cyan-600"
          />
          <button
            onClick={() => submit(input)}
            disabled={checking || !input}
            className="w-full bg-cyan-600 hover:bg-cyan-500 disabled:opacity-40 text-white text-sm font-medium py-2.5 rounded-lg transition-colors"
          >
            {checking ? "Checking…" : "Enter"}
          </button>
        </div>

        {error && (
          <p className="text-center text-sm text-red-400">{error}</p>
        )}

        <p className="text-center text-xs text-zinc-700">
          <Link href="/" className="hover:text-zinc-500 transition-colors">← Back to dashboard</Link>
        </p>
      </div>
    </div>
  );
}

// ─── Authenticated picks view ─────────────────────────────────────────────────

function PicksView({ onLogout }: { onLogout: () => void }) {
  const [selectedTicker, setSelectedTicker] = useState("");
  const [generatedAt, setGeneratedAt] = useState<string | null>(null);
  const [refreshing, setRefreshing] = useState(false);
  const [fetchKey, setFetchKey] = useState(0);
  const router = useRouter();

  const { data: quote } = useData(
    () => selectedTicker ? api.quote(selectedTicker) as Promise<any> : Promise.resolve(null),
    [selectedTicker],
    { refreshInterval: selectedTicker ? 60000 : 0 }
  );

  const { data: status } = useData(
    () => api.aiPicksStatus() as Promise<any>,
    [fetchKey],
    { refreshInterval: 0 }
  );

  useEffect(() => {
    if (status?.generated_at) setGeneratedAt(status.generated_at);
  }, [status]);

  const handleTickerSelect = useCallback((ticker: string) => {
    setSelectedTicker(ticker);
  }, []);

  const handleSimulate = (ticker: string) => {
    router.push(`/simulator?ticker=${encodeURIComponent(ticker)}`);
  };

  const handleRefresh = async () => {
    if (refreshing) return;
    setRefreshing(true);
    try {
      await api.aiRefresh();
      setFetchKey((k) => k + 1);
    } catch {}
    finally { setRefreshing(false); }
  };

  const cacheAge = useMemo(
    () => (generatedAt ? formatAge(generatedAt) : null),
    [generatedAt]
  );

  return (
    <div className="min-h-screen bg-zinc-950">
      <header className="border-b border-zinc-800 bg-zinc-950/90 backdrop-blur-sm sticky top-0 z-20">
        <div className="max-w-[1600px] mx-auto px-3 py-2.5 flex items-center gap-3 flex-wrap">
          <Link href="/" className="text-base font-bold text-cyan-400 hover:text-cyan-300 transition-colors">
            daydream
          </Link>
          <span className="text-base font-light text-zinc-400 hidden sm:inline">believer</span>
          <span className="text-zinc-700 hidden sm:inline">/</span>
          <span className="text-sm text-zinc-300">AI Picks</span>

          <div className="ml-auto flex items-center gap-3">
            {/* Cache age notice */}
            {cacheAge && (
              <div className="flex items-center gap-1.5 text-xs text-zinc-500">
                <Clock size={11} />
                <span>Generated {cacheAge}</span>
              </div>
            )}
            {status?.generating && (
              <span className="text-xs text-cyan-500 flex items-center gap-1">
                <RefreshCw size={10} className="animate-spin" /> Generating…
              </span>
            )}

            {/* Manual refresh */}
            <button
              onClick={handleRefresh}
              disabled={refreshing || status?.generating}
              className="flex items-center gap-1.5 text-xs text-zinc-400 hover:text-cyan-400 border border-zinc-700 hover:border-cyan-700/50 px-2.5 py-1.5 rounded-lg transition-colors disabled:opacity-40"
            >
              <RefreshCw size={10} className={refreshing ? "animate-spin" : ""} />
              Refresh Picks
            </button>

            <Link
              href="/simulator"
              className="flex items-center gap-1.5 text-xs text-zinc-400 hover:text-emerald-400 border border-zinc-700 hover:border-emerald-700/50 px-2.5 py-1.5 rounded-lg transition-colors"
            >
              <TrendingUp size={11} />
              Paper Trader
            </Link>
          </div>
        </div>
      </header>

      <div className="max-w-[1600px] mx-auto px-3 md:px-4 py-4">
        <div className="grid grid-cols-1 lg:grid-cols-[3fr_2fr] gap-4 items-start">
          <AIPicks
            onTickerSelect={handleTickerSelect}
            onSimulate={handleSimulate}
          />

          <div className={`lg:sticky lg:top-16 space-y-0 ${selectedTicker ? "block" : "hidden lg:block"}`}>
            <StockChart ticker={selectedTicker} height={500} />
            {quote && <StockInfoBar quote={quote} />}
            {selectedTicker && (
              <div className="mt-2 flex justify-end">
                <Link
                  href={`/simulator?ticker=${encodeURIComponent(selectedTicker)}`}
                  className="flex items-center gap-1.5 text-xs text-zinc-500 hover:text-emerald-400 transition-colors"
                >
                  <TrendingUp size={11} />
                  Trade {selectedTicker} in Paper Trader →
                </Link>
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}

// ─── Page root ────────────────────────────────────────────────────────────────

export default function PicksPage() {
  const [authenticated, setAuthenticated] = useState<boolean | null>(null); // null = checking

  useEffect(() => {
    const stored = localStorage.getItem("picks_passcode");
    if (!stored) {
      setAuthenticated(false);
      return;
    }
    // Silently verify the stored passcode
    api.verifyPasscode(stored)
      .then(() => setAuthenticated(true))
      .catch(() => {
        localStorage.removeItem("picks_passcode");
        setAuthenticated(false);
      });
  }, []);

  const handleLogout = () => {
    localStorage.removeItem("picks_passcode");
    setAuthenticated(false);
  };

  // Loading state while checking stored passcode
  if (authenticated === null) {
    return (
      <div className="min-h-screen bg-zinc-950 flex items-center justify-center">
        <div className="w-5 h-5 border-2 border-zinc-700 border-t-cyan-500 rounded-full animate-spin" />
      </div>
    );
  }

  if (!authenticated) {
    return <PasscodeGate onAuth={() => setAuthenticated(true)} />;
  }

  return <PicksView onLogout={handleLogout} />;
}
