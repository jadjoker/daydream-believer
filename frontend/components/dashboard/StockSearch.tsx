"use client";
import React, { useState, useEffect, useRef, useCallback } from "react";
import { useData } from "@/hooks/useData";
import { api } from "@/lib/api";
import { formatPrice, formatMarketCap } from "@/lib/utils";
import {
  Search, Sparkles, X, TrendingUp, TrendingDown, Minus,
  SendHorizonal, Bot, User, Loader2, ChevronDown, ChevronUp,
  Target, ShieldAlert, ArrowUpRight, RotateCcw,
} from "lucide-react";

interface StockSearchProps {
  onTickerSelect: (ticker: string) => void;
}

interface SearchResult {
  ticker: string;
  name: string;
  exchange: string;
  type: string;
}

interface ChatMsg {
  role: "user" | "assistant";
  content: string;
}

interface UnifiedAnalysis {
  recommendation: string;
  hold_horizon: string;
  trade_type: string;
  entry_low: number;
  entry_high: number;
  stop_loss: number;
  target: number;
  risk_reward: string;
  confidence: number;
  thesis: string;
  catalyst: string;
  key_risk: string;
}

// ─── Inline markdown renderer ─────────────────────────────────────────────────

function renderInline(text: string): React.ReactNode[] {
  const parts = text.split(/(\*\*[^*]+\*\*)/g);
  return parts.map((part, i) => {
    if (part.startsWith("**") && part.endsWith("**")) {
      return <strong key={i} className="font-semibold text-zinc-100">{part.slice(2, -2)}</strong>;
    }
    return part;
  });
}

function MdMessage({ content }: { content: string }) {
  const lines = content.split("\n");
  const nodes: React.ReactNode[] = [];
  let i = 0;

  while (i < lines.length) {
    const line = lines[i];
    const trimmed = line.trim();

    if (!trimmed) {
      if (nodes.length > 0 && i < lines.length - 1) {
        nodes.push(<div key={`sp-${i}`} className="h-1.5" />);
      }
    } else if (/^[-•]\s/.test(trimmed)) {
      const bullets: string[] = [];
      while (i < lines.length && /^[-•]\s/.test(lines[i].trim())) {
        bullets.push(lines[i].trim().replace(/^[-•]\s/, ""));
        i++;
      }
      nodes.push(
        <ul key={`ul-${i}`} className="space-y-1 pl-3">
          {bullets.map((b, bi) => (
            <li key={bi} className="flex gap-1.5">
              <span className="text-zinc-600 shrink-0 mt-0.5">•</span>
              <span>{renderInline(b)}</span>
            </li>
          ))}
        </ul>
      );
      continue;
    } else if (/^\d+\.\s/.test(trimmed)) {
      const items: string[] = [];
      while (i < lines.length && /^\d+\.\s/.test(lines[i].trim())) {
        items.push(lines[i].trim().replace(/^\d+\.\s/, ""));
        i++;
      }
      nodes.push(
        <ol key={`ol-${i}`} className="space-y-1 pl-3 list-decimal list-inside">
          {items.map((item, ii) => (
            <li key={ii}>{renderInline(item)}</li>
          ))}
        </ol>
      );
      continue;
    } else {
      nodes.push(<p key={`p-${i}`}>{renderInline(trimmed)}</p>);
    }
    i++;
  }

  return <div className="space-y-1 leading-relaxed">{nodes}</div>;
}

// ─── Recommendation badge ─────────────────────────────────────────────────────

function RecBadge({ rec }: { rec: string }) {
  const cfg: Record<string, { cls: string; label: string }> = {
    buy:   { cls: "bg-emerald-500/15 text-emerald-400 border-emerald-500/40", label: "BUY" },
    hold:  { cls: "bg-yellow-500/15 text-yellow-400 border-yellow-500/40",   label: "HOLD" },
    avoid: { cls: "bg-red-500/15 text-red-400 border-red-500/40",             label: "AVOID" },
  };
  const { cls, label } = cfg[rec?.toLowerCase()] ?? cfg.hold;
  return (
    <span className={`text-[10px] font-bold px-1.5 py-0.5 rounded-md border tracking-wide ${cls}`}>
      {label}
    </span>
  );
}

const POPULAR = ["AAPL", "MSFT", "NVDA", "TSLA", "META", "GOOGL", "AMZN", "SPY", "QQQ"];

// ─── Main component ───────────────────────────────────────────────────────────

export default function StockSearch({ onTickerSelect }: StockSearchProps) {
  const [query, setQuery] = useState("");
  const [results, setResults] = useState<SearchResult[]>([]);
  const [isSearching, setIsSearching] = useState(false);
  const [showDropdown, setShowDropdown] = useState(false);
  const [selectedTicker, setSelectedTicker] = useState("");
  const [analysis, setAnalysis] = useState<{ ticker: string; unified?: UnifiedAnalysis } | null>(null);
  const [isAnalyzing, setIsAnalyzing] = useState(false);
  const [showFullAnalysis, setShowFullAnalysis] = useState(true);
  const [messages, setMessages] = useState<ChatMsg[]>([]);
  const [chatInput, setChatInput] = useState("");
  const [isChatting, setIsChatting] = useState(false);

  const searchRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLInputElement>(null);
  const chatEndRef = useRef<HTMLDivElement>(null);
  const searchTimer = useRef<ReturnType<typeof setTimeout> | undefined>(undefined);
  // Prevents re-triggering search after programmatic query update on selection
  const justSelected = useRef(false);

  const { data: quote } = useData(
    () => selectedTicker ? api.quote(selectedTicker) as Promise<any> : Promise.resolve(null),
    [selectedTicker],
    { refreshInterval: selectedTicker ? 60000 : 0 }
  );

  // Debounced search — skips if query was set by selectTicker
  useEffect(() => {
    clearTimeout(searchTimer.current);
    const q = query.trim();
    if (!q) { setResults([]); setShowDropdown(false); return; }
    if (justSelected.current) { justSelected.current = false; return; }
    searchTimer.current = setTimeout(async () => {
      setIsSearching(true);
      try {
        const data = await api.searchTicker(q) as any;
        const res = ((data.results || []) as SearchResult[]).slice(0, 8);
        setResults(res);
        setShowDropdown(res.length > 0);
      } catch {
        setResults([]);
      } finally {
        setIsSearching(false);
      }
    }, 280);
    return () => clearTimeout(searchTimer.current);
  }, [query]);

  // Close dropdown on outside click/touch
  useEffect(() => {
    const handler = (e: MouseEvent | TouchEvent) => {
      if (searchRef.current && !searchRef.current.contains(e.target as Node)) {
        setShowDropdown(false);
      }
    };
    document.addEventListener("mousedown", handler);
    document.addEventListener("touchstart", handler);
    return () => {
      document.removeEventListener("mousedown", handler);
      document.removeEventListener("touchstart", handler);
    };
  }, []);

  // Scroll chat to bottom
  useEffect(() => {
    chatEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, isChatting]);

  const selectTicker = useCallback((ticker: string) => {
    justSelected.current = true;   // suppress the upcoming query-change search
    setSelectedTicker(ticker);
    setQuery(ticker);
    setShowDropdown(false);
    setResults([]);
    setAnalysis(null);
    setMessages([]);
    inputRef.current?.blur();      // dismiss keyboard on mobile
    onTickerSelect(ticker);
  }, [onTickerSelect]);

  const clearSearch = useCallback(() => {
    justSelected.current = false;
    setQuery("");
    setResults([]);
    setShowDropdown(false);
    setSelectedTicker("");
    setAnalysis(null);
    setMessages([]);
    onTickerSelect("");
    setTimeout(() => inputRef.current?.focus(), 50);
  }, [onTickerSelect]);

  const handleAnalyze = async () => {
    if (!selectedTicker || isAnalyzing) return;
    setIsAnalyzing(true);
    setAnalysis(null);
    setMessages([]);
    try {
      const result = await api.analyzeTickerAll(selectedTicker) as any;
      setAnalysis(result);
    } catch {
      setAnalysis({ ticker: selectedTicker });
    } finally {
      setIsAnalyzing(false);
    }
  };

  const sendChat = async (text: string) => {
    const q = text.trim();
    if (!q || isChatting || !selectedTicker) return;
    setChatInput("");
    const updated: ChatMsg[] = [...messages, { role: "user", content: q }];
    setMessages(updated);
    setIsChatting(true);
    try {
      const u = analysis?.unified;
      const ctx = u
        ? `Recommendation: ${u.recommendation?.toUpperCase()} | Horizon: ${u.hold_horizon} | Confidence: ${u.confidence}/10\nThesis: ${u.thesis}\nCatalyst: ${u.catalyst}\nKey risk: ${u.key_risk}\nEntry: $${u.entry_low}–$${u.entry_high} | Stop: $${u.stop_loss} | Target: $${u.target}`
        : "";
      const res = await api.aiChat(selectedTicker, q, updated.slice(0, -1), ctx) as any;
      setMessages(prev => [...prev, { role: "assistant", content: res.answer }]);
    } catch {
      setMessages(prev => [...prev, { role: "assistant", content: "Couldn't process that — please try again." }]);
    } finally {
      setIsChatting(false);
    }
  };

  const handleChat = () => sendChat(chatInput);

  const changePct = (quote as any)?.change_pct ?? 0;
  const isSearching_ = isSearching;

  return (
    <div className="space-y-3">

      {/* ── Search input ──────────────────────────────────────────────────── */}
      <div ref={searchRef} className="relative">
        <div className={`flex items-center gap-2.5 bg-zinc-900 border rounded-xl px-3.5 transition-all duration-200 ${
          showDropdown || (query && !selectedTicker)
            ? "border-cyan-700/70 shadow-lg shadow-cyan-950/30"
            : "border-zinc-800 hover:border-zinc-700/80"
        }`}>
          <Search
            size={15}
            className={`shrink-0 transition-colors duration-200 ${query ? "text-cyan-400" : "text-zinc-500"}`}
          />
          <input
            ref={inputRef}
            type="text"
            value={query}
            onChange={e => setQuery(e.target.value)}
            onFocus={() => { if (results.length > 0 && !selectedTicker) setShowDropdown(true); }}
            onKeyDown={e => {
              if (e.key === "Escape") { setShowDropdown(false); inputRef.current?.blur(); }
              if (e.key === "Enter" && results.length > 0) selectTicker(results[0].ticker);
            }}
            placeholder={selectedTicker ? `${selectedTicker} — tap × to change` : "Search stocks, ETFs…"}
            className="flex-1 bg-transparent text-sm text-zinc-100 placeholder-zinc-500 outline-none min-w-0 py-3"
            autoComplete="off"
            autoCapitalize="characters"
            spellCheck={false}
          />
          {isSearching_ && <Loader2 size={13} className="text-cyan-500 animate-spin shrink-0" />}
          {query && !isSearching_ && (
            <button
              onClick={clearSearch}
              className="text-zinc-500 hover:text-zinc-200 active:text-zinc-100 transition-colors shrink-0 p-2 -mr-1 rounded-lg"
              aria-label="Clear search"
            >
              <X size={14} />
            </button>
          )}
        </div>

        {/* Dropdown */}
        {showDropdown && results.length > 0 && (
          <div className="absolute top-full mt-2 left-0 right-0 bg-zinc-900/97 backdrop-blur-md border border-zinc-700/70 rounded-xl shadow-2xl shadow-black/60 z-40 overflow-hidden">
            {results.map(r => (
              <button
                key={r.ticker}
                onMouseDown={e => { e.preventDefault(); selectTicker(r.ticker); }}
                onTouchEnd={e => { e.preventDefault(); selectTicker(r.ticker); }}
                className="w-full flex items-center gap-3 px-4 py-3.5 hover:bg-zinc-800/60 active:bg-zinc-800 transition-colors text-left group border-b border-zinc-800/50 last:border-0"
              >
                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-2 flex-wrap">
                    <span className="text-sm font-bold text-zinc-100 group-hover:text-cyan-400 transition-colors">{r.ticker}</span>
                    <span className="text-[10px] text-zinc-600 bg-zinc-800 px-1.5 py-0.5 rounded">{r.exchange}</span>
                    {r.type && r.type !== "Common Stock" && r.type !== "EQUITY" && (
                      <span className="text-[10px] text-zinc-600">{r.type}</span>
                    )}
                  </div>
                  <span className="text-xs text-zinc-500 truncate block leading-none mt-0.5">{r.name}</span>
                </div>
                <ArrowUpRight size={13} className="text-zinc-700 group-hover:text-cyan-500 transition-colors shrink-0" />
              </button>
            ))}
          </div>
        )}
      </div>

      {/* Quick-pick chips — only when nothing selected */}
      {!selectedTicker && (
        <div className="flex flex-wrap gap-1.5">
          {POPULAR.map(t => (
            <button
              key={t}
              onClick={() => selectTicker(t)}
              className="text-xs px-3 py-1.5 rounded-md border border-zinc-700/60 bg-zinc-800/50 text-zinc-500 hover:text-zinc-200 hover:bg-zinc-800 hover:border-zinc-600 active:bg-zinc-700 transition-colors"
            >
              {t}
            </button>
          ))}
        </div>
      )}

      {/* ── Selected stock card ───────────────────────────────────────────── */}
      {selectedTicker && (
        <div className="bg-zinc-900 border border-zinc-800 rounded-xl p-4 space-y-3">
          {/* Header row */}
          <div className="flex items-start justify-between gap-3">
            <div className="min-w-0 flex-1">
              <div className="flex items-center gap-2 flex-wrap">
                <span className="text-base font-bold text-zinc-100 tracking-tight">{selectedTicker}</span>
                {(quote as any)?.sector && (
                  <span className="text-[10px] text-zinc-500 bg-zinc-800 px-1.5 py-0.5 rounded-md border border-zinc-700/50 truncate max-w-[120px]">
                    {(quote as any).sector}
                  </span>
                )}
              </div>
              {(quote as any)?.name && (
                <div className="text-xs text-zinc-500 mt-0.5 truncate pr-2">{(quote as any).name}</div>
              )}
            </div>
            <div className="text-right shrink-0">
              {(quote as any)?.price != null ? (
                <>
                  <div className="text-lg font-bold text-zinc-100 tabular-nums leading-none">{formatPrice((quote as any).price)}</div>
                  <div className={`text-xs font-medium tabular-nums flex items-center justify-end gap-0.5 mt-0.5 ${
                    changePct > 0 ? "text-emerald-400" : changePct < 0 ? "text-red-400" : "text-zinc-500"
                  }`}>
                    {changePct > 0 ? <TrendingUp size={11} /> : changePct < 0 ? <TrendingDown size={11} /> : <Minus size={11} />}
                    {changePct >= 0 ? "+" : ""}{changePct.toFixed(2)}%
                  </div>
                </>
              ) : (
                <div className="text-xs text-zinc-600 animate-pulse mt-1">Loading…</div>
              )}
            </div>
          </div>

          {/* Quick stats */}
          {quote && (
            <div className="grid grid-cols-3 gap-2">
              {[
                { label: "Mkt Cap",  value: formatMarketCap((quote as any).market_cap) },
                { label: "P/E",      value: (quote as any).pe_ratio != null ? (quote as any).pe_ratio.toFixed(1) : "—" },
                { label: "52w Range", value: (quote as any).week_52_low != null
                    ? `${formatPrice((quote as any).week_52_low)}–${formatPrice((quote as any).week_52_high)}`
                    : "—" },
              ].map(s => (
                <div key={s.label} className="bg-zinc-800/50 rounded-lg px-2.5 py-2">
                  <div className="text-[10px] text-zinc-500 leading-none">{s.label}</div>
                  <div className="text-xs font-semibold text-zinc-200 tabular-nums truncate mt-1">{s.value}</div>
                </div>
              ))}
            </div>
          )}

          {/* Action buttons */}
          <div className="flex gap-2">
            <button
              onClick={handleAnalyze}
              disabled={isAnalyzing}
              className="flex-1 flex items-center justify-center gap-2 bg-cyan-600 hover:bg-cyan-500 active:bg-cyan-700 disabled:opacity-50 text-white text-sm font-medium py-2.5 rounded-lg transition-all duration-150"
            >
              {isAnalyzing
                ? <><Loader2 size={13} className="animate-spin" />Analyzing…</>
                : <><Sparkles size={13} />Analyze with AI</>
              }
            </button>
            <button
              onClick={clearSearch}
              className="flex items-center justify-center gap-1.5 text-xs text-zinc-500 hover:text-zinc-200 active:text-zinc-100 border border-zinc-700/60 hover:border-zinc-600 px-3 py-2.5 rounded-lg transition-colors"
              aria-label="Change stock"
            >
              <RotateCcw size={12} />
              <span className="hidden sm:inline">Change</span>
            </button>
          </div>
        </div>
      )}

      {/* ── Analysis card ─────────────────────────────────────────────────── */}
      {analysis?.unified && (
        <div className="bg-zinc-900 border border-zinc-800 rounded-xl overflow-hidden">
          <button
            className="w-full flex items-center gap-3 px-4 py-3.5 hover:bg-zinc-800/30 active:bg-zinc-800/50 transition-colors border-b border-zinc-800 text-left"
            onClick={() => setShowFullAnalysis(v => !v)}
          >
            <Sparkles size={12} className="text-cyan-400 shrink-0" />
            <div className="flex items-center gap-2 flex-1 min-w-0 flex-wrap">
              <RecBadge rec={analysis.unified.recommendation} />
              <span className="text-xs text-zinc-400">{analysis.unified.hold_horizon}</span>
              <span className="text-zinc-700 text-xs">·</span>
              <span className="text-xs text-zinc-500">{analysis.unified.confidence}/10 confidence</span>
            </div>
            {showFullAnalysis
              ? <ChevronUp size={14} className="text-zinc-600 shrink-0" />
              : <ChevronDown size={14} className="text-zinc-600 shrink-0" />}
          </button>

          {showFullAnalysis && (
            <div className="px-4 py-4 space-y-3">
              <p className="text-xs text-zinc-300 leading-relaxed">{analysis.unified.thesis}</p>

              <div className="grid grid-cols-2 gap-2">
                {[
                  { icon: <Target size={9} />, label: "Entry", value: `$${analysis.unified.entry_low}–$${analysis.unified.entry_high}`, cls: "text-cyan-300" },
                  { icon: null,                label: "Target", value: `$${analysis.unified.target}`,                                    cls: "text-emerald-300" },
                  { icon: <ShieldAlert size={9} />, label: "Stop", value: `$${analysis.unified.stop_loss}`,                              cls: "text-red-300" },
                  { icon: null,                label: "R/R",    value: analysis.unified.risk_reward,                                     cls: "text-zinc-200" },
                ].map(item => (
                  <div key={item.label} className="bg-zinc-800/40 border border-zinc-700/30 rounded-lg p-3">
                    <div className="flex items-center gap-1 text-[10px] text-zinc-500 mb-1.5">
                      {item.icon}{item.label}
                    </div>
                    <div className={`text-xs font-semibold tabular-nums ${item.cls}`}>{item.value}</div>
                  </div>
                ))}
              </div>

              {analysis.unified.catalyst && (
                <p className="text-xs text-zinc-400 leading-relaxed">
                  <span className="text-zinc-600">Catalyst: </span>{analysis.unified.catalyst}
                </p>
              )}
              {analysis.unified.key_risk && (
                <p className="text-xs text-zinc-400 leading-relaxed">
                  <span className="text-zinc-600">Key risk: </span>{analysis.unified.key_risk}
                </p>
              )}
            </div>
          )}
        </div>
      )}

      {/* ── Chat section ──────────────────────────────────────────────────── */}
      {analysis?.unified && (
        <div className="bg-zinc-900 border border-zinc-800 rounded-xl overflow-hidden">
          <div className="px-4 py-3 border-b border-zinc-800 flex items-center gap-2">
            <Bot size={13} className="text-cyan-500 shrink-0" />
            <span className="text-xs text-zinc-400 font-medium">Ask follow-up questions</span>
          </div>

          {messages.length > 0 && (
            <div className="px-4 py-3 space-y-3 max-h-80 overflow-y-auto overscroll-contain">
              {messages.map((msg, i) => (
                <div key={i} className={`flex gap-2 ${msg.role === "user" ? "justify-end" : "justify-start"}`}>
                  {msg.role === "assistant" && (
                    <div className="w-6 h-6 rounded-full bg-cyan-500/20 border border-cyan-500/30 flex items-center justify-center shrink-0 mt-0.5">
                      <Bot size={11} className="text-cyan-400" />
                    </div>
                  )}
                  <div className={`max-w-[88%] rounded-2xl px-3.5 py-2.5 text-xs ${
                    msg.role === "user"
                      ? "bg-cyan-600/20 border border-cyan-700/30 text-cyan-100 leading-relaxed rounded-tr-sm"
                      : "bg-zinc-800 border border-zinc-700/40 text-zinc-200 rounded-tl-sm"
                  }`}>
                    {msg.role === "assistant"
                      ? <MdMessage content={msg.content} />
                      : msg.content}
                  </div>
                  {msg.role === "user" && (
                    <div className="w-6 h-6 rounded-full bg-zinc-800 border border-zinc-700/50 flex items-center justify-center shrink-0 mt-0.5">
                      <User size={11} className="text-zinc-400" />
                    </div>
                  )}
                </div>
              ))}
              {isChatting && (
                <div className="flex gap-2">
                  <div className="w-6 h-6 rounded-full bg-cyan-500/20 border border-cyan-500/30 flex items-center justify-center shrink-0">
                    <Bot size={11} className="text-cyan-400" />
                  </div>
                  <div className="bg-zinc-800 border border-zinc-700/40 rounded-2xl rounded-tl-sm px-4 py-3 flex gap-1.5 items-center">
                    {[0, 150, 300].map(d => (
                      <span
                        key={d}
                        className="w-1.5 h-1.5 bg-zinc-500 rounded-full animate-bounce"
                        style={{ animationDelay: `${d}ms` }}
                      />
                    ))}
                  </div>
                </div>
              )}
              <div ref={chatEndRef} />
            </div>
          )}

          {/* Suggestion chips */}
          {messages.length === 0 && !isChatting && (
            <div className="px-4 py-3 flex gap-2 flex-wrap">
              {["What's the growth thesis?", "What are the main risks?", "Is the valuation fair?"].map(s => (
                <button
                  key={s}
                  onClick={() => sendChat(s)}
                  className="text-[11px] text-zinc-500 hover:text-zinc-200 active:text-zinc-100 bg-zinc-800/60 hover:bg-zinc-800 border border-zinc-700/40 rounded-xl px-3 py-2 transition-colors"
                >
                  {s}
                </button>
              ))}
            </div>
          )}

          {/* Input row */}
          <div className="px-3 py-3 border-t border-zinc-800">
            <div className="flex items-center gap-2">
              <input
                type="text"
                value={chatInput}
                onChange={e => setChatInput(e.target.value)}
                onKeyDown={e => { if (e.key === "Enter" && !e.shiftKey) handleChat(); }}
                placeholder={`Ask about ${selectedTicker}…`}
                className="flex-1 bg-zinc-800/60 border border-zinc-700/50 rounded-xl px-3.5 py-2.5 text-xs text-zinc-200 placeholder-zinc-600 outline-none focus:border-cyan-700/60 transition-colors"
              />
              <button
                onClick={handleChat}
                disabled={!chatInput.trim() || isChatting}
                className="bg-cyan-600 hover:bg-cyan-500 active:bg-cyan-700 disabled:opacity-40 text-white p-2.5 rounded-xl transition-colors shrink-0"
                aria-label="Send message"
              >
                <SendHorizonal size={14} />
              </button>
            </div>
          </div>
        </div>
      )}

      {/* ── Empty state ───────────────────────────────────────────────────── */}
      {!selectedTicker && (
        <div className="flex flex-col items-center justify-center py-12 text-center">
          <div className="w-11 h-11 rounded-full bg-zinc-800/60 border border-zinc-700/40 flex items-center justify-center mb-3">
            <Search size={17} className="text-zinc-600" />
          </div>
          <p className="text-sm text-zinc-500">Search for any stock or ETF</p>
          <p className="text-xs text-zinc-700 mt-1">Chart updates as you select</p>
        </div>
      )}
    </div>
  );
}
