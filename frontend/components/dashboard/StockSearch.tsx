"use client";
import { useState, useCallback, useEffect, useRef } from "react";
import { Search, X, Loader2 } from "lucide-react";
import { api } from "@/lib/api";

interface SearchResult {
  ticker: string;
  name: string;
  exchange: string;
  type: string;
}

interface StockSearchProps {
  onSelect: (ticker: string) => void;
  currentTicker?: string;
}

const POPULAR = ["AAPL", "MSFT", "NVDA", "TSLA", "AMD", "META", "GOOGL", "AMZN", "SPY", "QQQ", "GME", "AMC"];

export default function StockSearch({ onSelect, currentTicker }: StockSearchProps) {
  const [value, setValue] = useState("");
  const [results, setResults] = useState<SearchResult[]>([]);
  const [searching, setSearching] = useState(false);
  const [open, setOpen] = useState(false);
  const debounceRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const containerRef = useRef<HTMLDivElement>(null);

  // Debounced search
  useEffect(() => {
    if (debounceRef.current) clearTimeout(debounceRef.current);
    if (value.length < 1) {
      setResults([]);
      setOpen(false);
      return;
    }
    setSearching(true);
    debounceRef.current = setTimeout(async () => {
      try {
        const data = await api.searchTicker(value) as any;
        setResults(data.results || []);
        setOpen(true);
      } catch {
        setResults([]);
      } finally {
        setSearching(false);
      }
    }, 300);
    return () => {
      if (debounceRef.current) clearTimeout(debounceRef.current);
    };
  }, [value]);

  // Close dropdown on outside click
  useEffect(() => {
    const handler = (e: MouseEvent) => {
      if (containerRef.current && !containerRef.current.contains(e.target as Node)) {
        setOpen(false);
      }
    };
    document.addEventListener("mousedown", handler);
    return () => document.removeEventListener("mousedown", handler);
  }, []);

  const handleSelect = useCallback((ticker: string) => {
    onSelect(ticker);
    setValue("");
    setResults([]);
    setOpen(false);
  }, [onSelect]);

  const handleSubmit = useCallback((e: React.FormEvent) => {
    e.preventDefault();
    // If there's a top result, use its ticker; otherwise treat input as raw ticker
    if (results.length > 0) {
      handleSelect(results[0].ticker);
    } else {
      const t = value.trim().toUpperCase();
      if (t) handleSelect(t);
    }
  }, [value, results, handleSelect]);

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === "Escape") {
      setOpen(false);
      setValue("");
    }
  };

  return (
    <div className="space-y-2">
      <div ref={containerRef} className="relative">
        <form onSubmit={handleSubmit} className="flex gap-2">
          <div className="relative flex-1">
            {searching
              ? <Loader2 size={14} className="absolute left-3 top-1/2 -translate-y-1/2 text-zinc-500 animate-spin" />
              : <Search size={14} className="absolute left-3 top-1/2 -translate-y-1/2 text-zinc-500" />
            }
            <input
              type="text"
              value={value}
              onChange={(e) => setValue(e.target.value)}
              onKeyDown={handleKeyDown}
              onFocus={() => results.length > 0 && setOpen(true)}
              placeholder="Search ticker or company… (e.g. Duluth, AAPL)"
              className="w-full bg-zinc-800 border border-zinc-700 rounded-lg pl-9 pr-3 py-2 text-sm text-zinc-100 placeholder-zinc-500 focus:outline-none focus:border-cyan-500/60 transition-colors"
            />
            {value && (
              <button
                type="button"
                onClick={() => { setValue(""); setResults([]); setOpen(false); }}
                className="absolute right-2 top-1/2 -translate-y-1/2 text-zinc-500 hover:text-zinc-300"
              >
                <X size={14} />
              </button>
            )}
          </div>
          <button
            type="submit"
            className="bg-cyan-600 hover:bg-cyan-500 text-white text-sm font-medium px-4 rounded-lg transition-colors"
          >
            Load
          </button>
        </form>

        {/* Autocomplete dropdown */}
        {open && results.length > 0 && (
          <div className="absolute top-full left-0 right-10 mt-1 bg-zinc-900 border border-zinc-700 rounded-xl shadow-xl z-50 overflow-hidden">
            {results.map((r) => (
              <button
                key={r.ticker}
                type="button"
                onMouseDown={(e) => { e.preventDefault(); handleSelect(r.ticker); }}
                className="w-full flex items-center justify-between px-4 py-2.5 hover:bg-zinc-800 transition-colors text-left"
              >
                <div className="flex items-center gap-3">
                  <span className="font-bold text-cyan-400 w-14 shrink-0">{r.ticker}</span>
                  <span className="text-sm text-zinc-300 truncate">{r.name}</span>
                </div>
                <div className="flex items-center gap-2 shrink-0 ml-2">
                  {r.type && r.type !== "EQUITY" && (
                    <span className="text-[10px] bg-zinc-800 text-zinc-500 px-1.5 py-0.5 rounded">{r.type}</span>
                  )}
                  <span className="text-xs text-zinc-600">{r.exchange}</span>
                </div>
              </button>
            ))}
          </div>
        )}
      </div>

      {/* Quick-pick chips */}
      <div className="flex flex-wrap gap-1.5">
        {POPULAR.map((t) => (
          <button
            key={t}
            onClick={() => handleSelect(t)}
            className={`text-xs px-2.5 py-1 rounded-md border transition-colors ${
              currentTicker === t
                ? "bg-cyan-600/30 border-cyan-500/60 text-cyan-300"
                : "bg-zinc-800 border-zinc-700 text-zinc-400 hover:text-zinc-200 hover:bg-zinc-700"
            }`}
          >
            {t}
          </button>
        ))}
      </div>
    </div>
  );
}
