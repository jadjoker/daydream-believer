"use client";
import { useState, useCallback, useEffect } from "react";
import { useSimulator } from "@/hooks/useSimulator";
import { useData } from "@/hooks/useData";
import { api } from "@/lib/api";
import {
  formatNum, formatPct, formatPrice, colorClass,
} from "@/lib/utils";
import { Card, StatCard } from "@/components/ui/Card";
import { Badge } from "@/components/ui/Badge";
import {
  TrendingUp, DollarSign, Target, RefreshCw,
  PlusCircle, History, BarChart2, AlertCircle, CheckCircle2, XCircle,
  Repeat2, Trash2, Play, LineChart,
} from "lucide-react";
import StockChart from "@/components/dashboard/StockChart";

interface SimulatorPanelProps {
  ticker: string;
}

type View = "trade" | "portfolio" | "history" | "accuracy" | "chart" | "recurring";

export default function SimulatorPanel({ ticker }: SimulatorPanelProps) {
  const { state, loading, buy, sell, addFunds, reset, refetch, stats } = useSimulator();
  const [view, setView] = useState<View>("chart");

  const { data: quote } = useData(
    () => ticker ? api.quote(ticker) as Promise<any> : Promise.resolve(null),
    [ticker],
    { refreshInterval: ticker ? 30000 : 0 }
  );

  const currentPrice = quote?.price ?? 0;

  const [priceMap, setPriceMap] = useState<Record<string, number>>({});
  const positionTickers = Object.keys(state?.positions ?? {}).sort().join(",");
  useEffect(() => {
    const tickers = Object.keys(state?.positions ?? {});
    if (tickers.length === 0) { setPriceMap({}); return; }
    api.multiQuote(tickers).then((data: any) => {
      const map: Record<string, number> = {};
      (data.quotes ?? []).forEach((q: any) => { if (q.price) map[q.ticker] = q.price; });
      setPriceMap(map);
    }).catch(() => {});
  }, [positionTickers]);

  const positionsValue = Object.entries(state.positions).reduce(
    (sum, [sym, pos]) => sum + pos.shares * (priceMap[sym] ?? pos.avgCost),
    0
  );
  const totalValue = state.cash + positionsValue;
  const totalReturn = totalValue - state.startingBalance;
  const totalReturnPct = (totalReturn / state.startingBalance) * 100;

  const VIEWS: { id: View; label: string; icon: React.ReactNode }[] = [
    { id: "trade",     label: "Trade",     icon: <DollarSign size={13} /> },
    { id: "chart",     label: "Chart",     icon: <LineChart size={13} /> },
    { id: "portfolio", label: "Portfolio", icon: <BarChart2 size={13} /> },
    { id: "history",   label: "History",   icon: <History size={13} /> },
    { id: "accuracy",  label: "Accuracy",  icon: <Target size={13} /> },
    { id: "recurring", label: "Recurring", icon: <Repeat2 size={13} /> },
  ];

  return (
    <div className="space-y-4">
      {/* Account summary bar */}
      <div className="bg-zinc-900 border border-zinc-800 rounded-xl p-4">
        <div className="flex items-center justify-between mb-3">
          <div className="flex items-center gap-2">
            <span className="text-sm font-semibold text-zinc-300">Paper Trading Simulator</span>
            <Badge variant="info">Virtual</Badge>
          </div>
          <div className="flex items-center gap-2">
            <button
              onClick={() => addFunds(10000)}
              className="flex items-center gap-1 text-xs text-zinc-400 hover:text-emerald-400 transition-colors"
              title="Add $10,000"
            >
              <PlusCircle size={12} /> +$10K
            </button>
            <button
              onClick={async () => { if (confirm("Reset simulator? All trades and positions will be lost.")) await reset(); }}
              className="flex items-center gap-1 text-xs text-zinc-600 hover:text-red-400 transition-colors"
            >
              <RefreshCw size={12} /> Reset
            </button>
          </div>
        </div>
        {loading && <div className="text-xs text-zinc-500 mb-2">Loading shared state…</div>}
        <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
          <StatCard label="Cash" value={`$${formatNum(state.cash, 2)}`} valueClass="text-zinc-200" />
          <StatCard label="Positions Value" value={`$${formatNum(positionsValue, 2)}`} valueClass="text-zinc-200" />
          <StatCard
            label="Total Value"
            value={`$${formatNum(totalValue, 2)}`}
            valueClass={colorClass(totalReturn)}
          />
          <StatCard
            label="Total Return"
            value={formatPct(totalReturnPct)}
            valueClass={colorClass(totalReturn)}
            sub={`${totalReturn >= 0 ? "+" : ""}$${formatNum(totalReturn, 2)}`}
          />
        </div>
      </div>

      {/* View tabs — scrollable on mobile to prevent horizontal overflow */}
      <div className="flex gap-1 overflow-x-auto pb-0.5 [&::-webkit-scrollbar]:hidden [-ms-overflow-style:none] [scrollbar-width:none]">
        {VIEWS.map((v) => (
          <button
            key={v.id}
            onClick={() => setView(v.id)}
            className={`flex items-center gap-1.5 px-3 py-2 rounded-lg text-sm font-medium transition-colors shrink-0 ${
              view === v.id
                ? "bg-zinc-800 text-zinc-100 border border-zinc-700"
                : "text-zinc-500 hover:text-zinc-300"
            }`}
          >
            {v.icon} {v.label}
          </button>
        ))}
      </div>

      {view === "trade" && (
        <TradeView ticker={ticker} quote={quote} currentPrice={currentPrice} state={state} buy={buy} sell={sell} />
      )}
      {view === "portfolio" && (
        <PortfolioView positions={state.positions} currentPrice={currentPrice} ticker={ticker} priceMap={priceMap} />
      )}
      {view === "history" && (
        <HistoryView trades={state.trades} />
      )}
      {view === "accuracy" && (
        <AccuracyView stats={stats} trades={state.trades} />
      )}
      {view === "chart" && (
        <ChartView ticker={ticker} quote={quote} />
      )}
      {view === "recurring" && (
        <RecurringView defaultTicker={ticker} onStateChange={refetch} />
      )}
    </div>
  );
}

// ─── Trade View ─────────────────────────────────────────────────────────────

function TradeView({
  ticker, quote, currentPrice, state, buy, sell,
}: {
  ticker: string;
  quote: any;
  currentPrice: number;
  state: any;
  buy: any;
  sell: any;
}) {
  if (!ticker) {
    return (
      <div className="grid grid-cols-1 xl:grid-cols-2 gap-4">
        <Card title="Trade">
          <div className="flex flex-col items-center justify-center py-16 text-zinc-600">
            <TrendingUp size={32} className="mb-3 opacity-30" />
            <p className="text-sm text-zinc-500">No stock selected</p>
            <p className="text-xs text-zinc-600 mt-1 text-center max-w-[200px]">
              Click a ticker or "Simulate →" from an AI pick to start trading
            </p>
          </div>
        </Card>
        <Card title="Position">
          <div className="flex flex-col items-center justify-center py-16 text-zinc-600">
            <BarChart2 size={32} className="mb-2 opacity-30" />
          </div>
        </Card>
      </div>
    );
  }

  const [action, setAction] = useState<"buy" | "sell">("buy");
  const [shares, setShares] = useState("");
  const [stopLoss, setStopLoss] = useState("");
  const [takeProfit, setTakeProfit] = useState("");
  const [maxRiskDollars, setMaxRiskDollars] = useState("");
  const [thesis, setThesis] = useState("");
  const [feedback, setFeedback] = useState<{ ok: boolean; msg: string } | null>(null);
  const [isSubmitting, setIsSubmitting] = useState(false);

  const sharesNum = parseFloat(shares) || 0;
  const stopNum = parseFloat(stopLoss) || 0;
  const tpNum = parseFloat(takeProfit) || 0;
  const riskPerShare = stopNum > 0 && currentPrice > 0 ? Math.abs(currentPrice - stopNum) : 0;
  const rewardPerShare = tpNum > 0 && currentPrice > 0 ? Math.abs(tpNum - currentPrice) : 0;
  const rrRatio = riskPerShare > 0 && rewardPerShare > 0 ? rewardPerShare / riskPerShare : 0;
  const total = sharesNum * currentPrice;
  const maxRisk = sharesNum > 0 && riskPerShare > 0 ? sharesNum * riskPerShare : 0;
  const maxReward = sharesNum > 0 && rewardPerShare > 0 ? sharesNum * rewardPerShare : 0;

  const position = state.positions[ticker.toUpperCase()];
  const maxSell = position?.shares ?? 0;
  const maxBuy = currentPrice > 0 ? Math.floor(state.cash / currentPrice) : 0;

  // Position sizer: given max $ risk and stop distance, compute share count
  const handleSizeByRisk = useCallback(() => {
    const riskAmt = parseFloat(maxRiskDollars);
    if (!riskAmt || !stopNum || !currentPrice) return;
    const riskPerSh = Math.abs(currentPrice - stopNum);
    if (riskPerSh <= 0) return;
    const computed = Math.floor(riskAmt / riskPerSh);
    setShares(String(Math.min(computed, maxBuy)));
  }, [maxRiskDollars, stopNum, currentPrice, maxBuy]);

  const handleSubmit = useCallback(async () => {
    if (isSubmitting) return;
    setFeedback(null);
    if (!sharesNum || sharesNum <= 0) {
      setFeedback({ ok: false, msg: "Enter a valid number of shares." });
      return;
    }
    setIsSubmitting(true);
    const name = quote?.name || ticker;
    const fullThesis = [
      thesis,
      stopNum ? `SL: ${formatPrice(stopNum)}` : "",
      tpNum ? `TP: ${formatPrice(tpNum)}` : "",
    ].filter(Boolean).join(" | ");
    try {
      const result = action === "buy"
        ? await buy(ticker, name, sharesNum, currentPrice, fullThesis)
        : await sell(ticker, name, sharesNum, currentPrice, fullThesis);

      setFeedback({
        ok: result.ok,
        msg: result.ok
          ? `${action === "buy" ? "Bought" : "Sold"} ${sharesNum} shares of ${ticker.toUpperCase()} @ ${formatPrice(currentPrice)}`
          : result.error ?? "Error",
      });
      if (result.ok) {
        setShares("");
        setThesis("");
      }
    } finally {
      setIsSubmitting(false);
    }
  }, [action, sharesNum, currentPrice, ticker, thesis, stopNum, tpNum, buy, sell, quote, isSubmitting]);

  return (
    <div className="grid grid-cols-1 xl:grid-cols-2 gap-4">
      {/* Order form */}
      <Card title={`${action === "buy" ? "Buy" : "Sell"} ${ticker.toUpperCase()}`}>
        <div className="space-y-4">
          {/* Buy / Sell toggle */}
          <div className="flex rounded-lg overflow-hidden border border-zinc-700">
            <button
              onClick={() => setAction("buy")}
              className={`flex-1 py-2 text-sm font-semibold transition-colors ${action === "buy" ? "bg-emerald-600 text-white" : "bg-zinc-800 text-zinc-500 hover:text-zinc-300"}`}
            >
              Buy
            </button>
            <button
              onClick={() => setAction("sell")}
              className={`flex-1 py-2 text-sm font-semibold transition-colors ${action === "sell" ? "bg-red-600 text-white" : "bg-zinc-800 text-zinc-500 hover:text-zinc-300"}`}
            >
              Sell
            </button>
          </div>

          {/* Price display */}
          <div className="bg-zinc-800/60 rounded-lg p-3">
            <div className="text-xs text-zinc-500 mb-1">Current Price</div>
            <div className="flex items-center justify-between">
              <span className="text-2xl font-bold tabular-nums">{formatPrice(currentPrice)}</span>
              {quote?.change_pct != null && (
                <span className={`text-sm font-medium ${colorClass(quote.change_pct)}`}>
                  {formatPct(quote.change_pct)}
                </span>
              )}
            </div>
          </div>

          {/* Stop Loss + Take Profit */}
          {action === "buy" && (
            <div className="grid grid-cols-2 gap-2">
              <div>
                <label className="text-xs text-zinc-500 block mb-1">Stop Loss</label>
                <input
                  type="number"
                  step="0.01"
                  value={stopLoss}
                  onChange={(e) => setStopLoss(e.target.value)}
                  placeholder={currentPrice > 0 ? (currentPrice * 0.98).toFixed(2) : "0.00"}
                  className="w-full bg-zinc-800 border border-red-900/40 rounded-lg px-3 py-2 text-sm text-red-300 focus:outline-none focus:border-red-500/60 placeholder-zinc-700"
                />
              </div>
              <div>
                <label className="text-xs text-zinc-500 block mb-1">Take Profit</label>
                <input
                  type="number"
                  step="0.01"
                  value={takeProfit}
                  onChange={(e) => setTakeProfit(e.target.value)}
                  placeholder={currentPrice > 0 ? (currentPrice * 1.04).toFixed(2) : "0.00"}
                  className="w-full bg-zinc-800 border border-emerald-900/40 rounded-lg px-3 py-2 text-sm text-emerald-300 focus:outline-none focus:border-emerald-500/60 placeholder-zinc-700"
                />
              </div>
            </div>
          )}

          {/* R/R display when both set */}
          {action === "buy" && rrRatio > 0 && (
            <div className={`flex items-center justify-between text-sm rounded-lg px-3 py-2 ${rrRatio >= 2 ? "bg-emerald-500/10 border border-emerald-900/40" : rrRatio >= 1 ? "bg-yellow-500/10 border border-yellow-900/40" : "bg-red-500/10 border border-red-900/40"}`}>
              <span className="text-zinc-400">Risk/Reward</span>
              <span className={`font-bold ${rrRatio >= 2 ? "text-emerald-400" : rrRatio >= 1 ? "text-yellow-400" : "text-red-400"}`}>
                1 : {rrRatio.toFixed(2)}
                {rrRatio < 1 && " ⚠ Poor setup"}
                {rrRatio >= 2 && " ✓ Good"}
              </span>
            </div>
          )}

          {/* Shares input */}
          <div>
            <div className="flex items-center justify-between mb-1.5">
              <label className="text-xs text-zinc-500">Shares</label>
              <div className="flex items-center gap-1.5">
                {action === "buy" && maxBuy > 0 && (
                  <>
                    {[0.25, 0.5, 1].map((pct) => (
                      <button
                        key={pct}
                        onClick={() => setShares(String(Math.floor(maxBuy * pct)))}
                        className="text-[10px] px-1.5 py-0.5 bg-zinc-800 border border-zinc-700 rounded text-zinc-400 hover:text-zinc-200 hover:bg-zinc-700 transition-colors"
                      >
                        {pct * 100}%
                      </button>
                    ))}
                  </>
                )}
                <span className="text-xs text-zinc-600">
                  {action === "buy" ? `Max: ${maxBuy}` : `Have: ${maxSell}`}
                </span>
              </div>
            </div>
            <input
              type="number"
              min="1"
              step="1"
              value={shares}
              onChange={(e) => setShares(e.target.value)}
              placeholder="0"
              className="w-full bg-zinc-800 border border-zinc-700 rounded-lg px-3 py-2 text-sm text-zinc-100 focus:outline-none focus:border-cyan-500/60"
            />
          </div>

          {/* Position sizer by max $ risk */}
          {action === "buy" && stopNum > 0 && (
            <div>
              <label className="text-xs text-zinc-500 block mb-1">Size by Max $ Risk</label>
              <div className="flex gap-2">
                <input
                  type="number"
                  min="0"
                  step="50"
                  value={maxRiskDollars}
                  onChange={(e) => setMaxRiskDollars(e.target.value)}
                  placeholder="e.g. 500"
                  className="flex-1 bg-zinc-800 border border-zinc-700 rounded-lg px-3 py-2 text-sm text-zinc-100 focus:outline-none focus:border-cyan-500/60"
                />
                <button
                  onClick={handleSizeByRisk}
                  disabled={!maxRiskDollars || !stopNum}
                  className="text-xs px-3 bg-cyan-700/30 border border-cyan-600/30 text-cyan-300 rounded-lg hover:bg-cyan-700/50 transition-colors disabled:opacity-40"
                >
                  Calculate
                </button>
              </div>
              {stopNum > 0 && riskPerShare > 0 && (
                <p className="text-xs text-zinc-600 mt-1">
                  Risk/share: {formatPrice(riskPerShare)}
                  {maxRiskDollars && ` → ${Math.floor(parseFloat(maxRiskDollars) / riskPerShare)} shares`}
                </p>
              )}
            </div>
          )}

          {/* Order total */}
          {sharesNum > 0 && (
            <div className="bg-zinc-800/40 rounded-lg p-3 space-y-1">
              <div className="flex justify-between text-sm">
                <span className="text-zinc-400">{sharesNum} × {formatPrice(currentPrice)}</span>
                <span className="font-semibold tabular-nums">${formatNum(total, 2)}</span>
              </div>
              {action === "buy" && (
                <div className="flex justify-between text-xs text-zinc-500">
                  <span>Remaining cash</span>
                  <span className={state.cash - total < 0 ? "text-red-400" : "text-zinc-400"}>
                    ${formatNum(state.cash - total, 2)}
                  </span>
                </div>
              )}
              {action === "buy" && maxRisk > 0 && (
                <div className="flex justify-between text-xs">
                  <span className="text-red-400/70">Max loss (at SL)</span>
                  <span className="text-red-400 font-medium">-${formatNum(maxRisk, 2)}</span>
                </div>
              )}
              {action === "buy" && maxReward > 0 && (
                <div className="flex justify-between text-xs">
                  <span className="text-emerald-400/70">Max gain (at TP)</span>
                  <span className="text-emerald-400 font-medium">+${formatNum(maxReward, 2)}</span>
                </div>
              )}
              {action === "sell" && position && (
                <div className="flex justify-between text-xs">
                  <span className="text-zinc-500">Realized P&L</span>
                  <span className={colorClass(total - sharesNum * position.avgCost)}>
                    {total - sharesNum * position.avgCost >= 0 ? "+" : ""}
                    ${formatNum(total - sharesNum * position.avgCost, 2)}
                  </span>
                </div>
              )}
            </div>
          )}

          {/* Thesis */}
          <div>
            <label className="text-xs text-zinc-500 block mb-1.5">
              Trade Thesis / Reason
              <span className="text-zinc-600 float-right">Tracked in Accuracy tab</span>
            </label>
            <textarea
              value={thesis}
              onChange={(e) => setThesis(e.target.value)}
              placeholder={`Why ${action === "buy" ? "buying" : "selling"} ${ticker.toUpperCase()}? (e.g. "RSI oversold, breakout above 200 SMA")`}
              rows={2}
              className="w-full bg-zinc-800 border border-zinc-700 rounded-lg px-3 py-2 text-sm text-zinc-100 placeholder-zinc-600 focus:outline-none focus:border-cyan-500/60 resize-none"
            />
          </div>

          {/* Feedback */}
          {feedback && (
            <div className={`flex items-start gap-2 text-sm rounded-lg px-3 py-2.5 ${feedback.ok ? "bg-emerald-500/15 text-emerald-400" : "bg-red-500/15 text-red-400"}`}>
              {feedback.ok ? <CheckCircle2 size={15} className="shrink-0 mt-0.5" /> : <AlertCircle size={15} className="shrink-0 mt-0.5" />}
              {feedback.msg}
            </div>
          )}

          {/* Submit */}
          <button
            onClick={handleSubmit}
            disabled={isSubmitting || !sharesNum || sharesNum <= 0 || !currentPrice}
            className={`w-full py-2.5 rounded-xl font-semibold text-sm transition-colors disabled:opacity-40 disabled:cursor-not-allowed ${
              action === "buy"
                ? "bg-emerald-600 hover:bg-emerald-500 text-white"
                : "bg-red-600 hover:bg-red-500 text-white"
            }`}
          >
            {isSubmitting ? "Processing…" : `${action === "buy" ? "Buy" : "Sell"} ${sharesNum > 0 ? `${sharesNum} shares` : ""} of ${ticker.toUpperCase()}`}
          </button>
        </div>
      </Card>

      {/* Current position for this ticker */}
      <Card title={`Position: ${ticker.toUpperCase()}`}>
        {position ? (
          <div className="space-y-3">
            <div className="grid grid-cols-2 gap-2">
              <StatCard label="Shares Held" value={formatNum(position.shares, 0)} />
              <StatCard label="Avg Cost" value={formatPrice(position.avgCost)} />
              <StatCard
                label="Market Value"
                value={`$${formatNum(position.shares * currentPrice, 2)}`}
                valueClass="text-zinc-200"
              />
              <StatCard
                label="Unrealized P&L"
                value={`${(position.shares * currentPrice - position.shares * position.avgCost) >= 0 ? "+" : ""}$${formatNum(position.shares * currentPrice - position.shares * position.avgCost, 2)}`}
                valueClass={colorClass(position.shares * currentPrice - position.shares * position.avgCost)}
                sub={formatPct(((currentPrice - position.avgCost) / position.avgCost) * 100)}
              />
            </div>
            <div className="bg-zinc-800/40 rounded-lg p-3">
              <div className="text-xs text-zinc-500 mb-2">Break-even price</div>
              <div className="text-lg font-semibold tabular-nums">{formatPrice(position.avgCost)}</div>
              <div className={`text-xs mt-1 ${currentPrice >= position.avgCost ? "text-emerald-400" : "text-red-400"}`}>
                Current price is {currentPrice >= position.avgCost ? "above" : "below"} break-even
              </div>
            </div>
          </div>
        ) : (
          <div className="flex flex-col items-center justify-center py-10 text-zinc-600">
            <BarChart2 size={28} className="mb-2 opacity-40" />
            <p className="text-sm">No position in {ticker.toUpperCase()}</p>
          </div>
        )}
      </Card>
    </div>
  );
}

// ─── Portfolio View ───────────────────────────────────────────────────────────

function PortfolioView({ positions, currentPrice, ticker, priceMap }: { positions: any; currentPrice: number; ticker: string; priceMap: Record<string, number> }) {
  const entries = Object.entries(positions) as [string, any][];

  if (entries.length === 0) {
    return (
      <Card title="Portfolio">
        <div className="flex flex-col items-center py-12 text-zinc-600">
          <BarChart2 size={32} className="mb-2 opacity-30" />
          <p>No open positions yet. Make a trade to get started.</p>
        </div>
      </Card>
    );
  }

  return (
    <Card title="Open Positions">
      <div className="overflow-auto">
        <table className="data-table">
          <thead>
            <tr>
              <th>Ticker</th>
              <th>Shares</th>
              <th>Avg Cost</th>
              <th>Current</th>
              <th>Mkt Value</th>
              <th>Unreal P&L</th>
              <th>Return %</th>
            </tr>
          </thead>
          <tbody>
            {entries.map(([sym, pos]) => {
              const price = priceMap[sym] ?? (sym === ticker.toUpperCase() ? currentPrice : 0);
              const mktVal = pos.shares * (price || pos.avgCost);
              const pnl = mktVal - pos.shares * pos.avgCost;
              const pct = ((price || pos.avgCost) - pos.avgCost) / pos.avgCost * 100;
              return (
                <tr key={sym}>
                  <td className="font-bold text-cyan-400">{sym}</td>
                  <td className="tabular-nums">{formatNum(pos.shares, 4)}</td>
                  <td className="tabular-nums">{formatPrice(pos.avgCost)}</td>
                  <td className="tabular-nums">{price ? formatPrice(price) : <span className="text-zinc-600">—</span>}</td>
                  <td className="tabular-nums">${formatNum(mktVal, 2)}</td>
                  <td className={`tabular-nums font-medium ${colorClass(pnl)}`}>
                    {pnl >= 0 ? "+" : ""}${formatNum(pnl, 2)}
                  </td>
                  <td className={`tabular-nums font-medium ${colorClass(pct)}`}>
                    {formatPct(pct)}
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </Card>
  );
}

// ─── History View ─────────────────────────────────────────────────────────────

function HistoryView({ trades }: { trades: any[] }) {
  if (trades.length === 0) {
    return (
      <Card title="Trade History">
        <div className="flex flex-col items-center py-12 text-zinc-600">
          <History size={32} className="mb-2 opacity-30" />
          <p>No trades yet.</p>
        </div>
      </Card>
    );
  }

  return (
    <Card title="Trade History" titleRight={<span className="text-zinc-500">{trades.length} trades</span>}>
      <div className="space-y-2 max-h-[500px] overflow-y-auto pr-1">
        {trades.map((t) => (
          <div key={t.id} className={`rounded-xl border p-3 ${
            t.action === "buy" ? "border-emerald-900/40 bg-emerald-950/20" : "border-red-900/40 bg-red-950/20"
          }`}>
            <div className="flex items-center justify-between mb-1">
              <div className="flex items-center gap-2">
                <Badge variant={t.action === "buy" ? "bullish" : "bearish"}>
                  {t.action.toUpperCase()}
                </Badge>
                <span className="font-bold text-cyan-400">{t.ticker}</span>
                <span className="text-sm text-zinc-300">{t.name}</span>
              </div>
              <div className="flex items-center gap-3 text-sm">
                {t.outcome && (
                  <div className="flex items-center gap-1">
                    {t.outcome === "win" ? <CheckCircle2 size={13} className="text-emerald-400" /> :
                     t.outcome === "loss" ? <XCircle size={13} className="text-red-400" /> :
                     <span className="text-zinc-500">—</span>}
                    {t.realizedPnl != null && (
                      <span className={`font-semibold tabular-nums ${colorClass(t.realizedPnl)}`}>
                        {t.realizedPnl >= 0 ? "+" : ""}${formatNum(t.realizedPnl, 2)} ({formatPct(t.realizedPnlPct ?? 0)})
                      </span>
                    )}
                  </div>
                )}
                <span className="text-xs text-zinc-600">{new Date(t.timestamp).toLocaleString()}</span>
              </div>
            </div>
            <div className="text-xs text-zinc-400 mb-1">
              {t.shares} shares @ {formatPrice(t.price)} = <span className="font-medium">${formatNum(t.total, 2)}</span>
            </div>
            {t.thesis && (
              <div className="text-xs text-zinc-500 italic bg-zinc-900/60 rounded px-2 py-1">
                "{t.thesis}"
              </div>
            )}
          </div>
        ))}
      </div>
    </Card>
  );
}

// ─── Accuracy View ────────────────────────────────────────────────────────────

function AccuracyView({ stats, trades }: { stats: any; trades: any[] }) {
  const closed = trades.filter((t) => t.action === "sell");

  return (
    <div className="space-y-4">
      {/* Summary stats */}
      <Card title="Prediction Accuracy">
        <div className="space-y-4">
          <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
            <div className="bg-zinc-800/50 rounded-xl p-4 text-center">
              <div className="text-3xl font-bold tabular-nums text-cyan-400">
                {stats.winRate.toFixed(1)}%
              </div>
              <div className="text-xs text-zinc-500 mt-1">Win Rate</div>
              <div className="text-xs text-zinc-600 mt-0.5">{stats.wins}W / {stats.losses}L</div>
            </div>
            <div className="bg-zinc-800/50 rounded-xl p-4 text-center">
              <div className={`text-3xl font-bold tabular-nums ${colorClass(stats.totalRealizedPnl)}`}>
                {stats.totalRealizedPnl >= 0 ? "+" : ""}${formatNum(stats.totalRealizedPnl, 0)}
              </div>
              <div className="text-xs text-zinc-500 mt-1">Total Realized P&L</div>
              <div className="text-xs text-zinc-600 mt-0.5">{stats.totalTrades} closed trades</div>
            </div>
            <div className="bg-zinc-800/50 rounded-xl p-4 text-center">
              <div className="text-3xl font-bold tabular-nums text-zinc-300">
                {stats.totalTrades > 0 ? formatNum(stats.avgWinPct / Math.abs(stats.avgLossPct || 1), 2) : "—"}
              </div>
              <div className="text-xs text-zinc-500 mt-1">Win/Loss Ratio</div>
              <div className="text-xs text-zinc-600 mt-0.5">Avg win / Avg loss</div>
            </div>
          </div>

          <div className="grid grid-cols-2 gap-3">
            <StatCard
              label="Avg Winning Trade"
              value={stats.wins > 0 ? formatPct(stats.avgWinPct) : "—"}
              valueClass="text-emerald-400"
            />
            <StatCard
              label="Avg Losing Trade"
              value={stats.losses > 0 ? formatPct(stats.avgLossPct) : "—"}
              valueClass="text-red-400"
            />
          </div>

          {/* Win rate bar */}
          {stats.totalTrades > 0 && (
            <div>
              <div className="flex justify-between text-xs text-zinc-500 mb-1">
                <span className="text-emerald-500">{stats.wins} wins</span>
                <span className="text-red-500">{stats.losses} losses</span>
              </div>
              <div className="h-3 bg-zinc-800 rounded-full overflow-hidden flex">
                <div
                  className="h-full bg-emerald-500/80 transition-all"
                  style={{ width: `${stats.winRate}%` }}
                />
                <div
                  className="h-full bg-red-500/80 transition-all"
                  style={{ width: `${100 - stats.winRate}%` }}
                />
              </div>
            </div>
          )}
        </div>
      </Card>

      {/* Per-trade thesis review */}
      {closed.length > 0 && (
        <Card title="Trade Review — Thesis vs Outcome">
          <div className="space-y-3 max-h-80 overflow-y-auto pr-1">
            {closed.map((t) => (
              <div key={t.id} className={`rounded-lg border p-3 ${
                t.outcome === "win" ? "border-emerald-800/60" :
                t.outcome === "loss" ? "border-red-800/60" : "border-zinc-800"
              }`}>
                <div className="flex items-center justify-between mb-2">
                  <div className="flex items-center gap-2">
                    {t.outcome === "win"
                      ? <CheckCircle2 size={14} className="text-emerald-400" />
                      : <XCircle size={14} className="text-red-400" />
                    }
                    <span className="font-bold text-sm">{t.ticker}</span>
                    <span className="text-xs text-zinc-500">{new Date(t.timestamp).toLocaleDateString()}</span>
                  </div>
                  <span className={`text-sm font-semibold tabular-nums ${colorClass(t.realizedPnl)}`}>
                    {t.realizedPnl >= 0 ? "+" : ""}${formatNum(t.realizedPnl, 2)} ({formatPct(t.realizedPnlPct ?? 0)})
                  </span>
                </div>
                {t.thesis && (
                  <div className="text-xs text-zinc-400 italic">"{t.thesis}"</div>
                )}
              </div>
            ))}
          </div>
        </Card>
      )}

      {closed.length === 0 && (
        <Card title="Trade Review">
          <div className="flex flex-col items-center py-10 text-zinc-600">
            <Target size={28} className="mb-2 opacity-30" />
            <p className="text-sm">Close a trade to see accuracy tracking here.</p>
          </div>
        </Card>
      )}
    </div>
  );
}

// ─── Chart View ───────────────────────────────────────────────────────────────

function ChartView({ ticker, quote }: { ticker: string; quote: any }) {
  if (!ticker) {
    return (
      <div className="bg-zinc-900 border border-zinc-800 rounded-xl flex flex-col items-center justify-center py-20 text-zinc-600">
        <LineChart size={32} className="mb-3 opacity-30" />
        <p className="text-sm text-zinc-500">No stock selected</p>
        <p className="text-xs text-zinc-600 mt-1 text-center max-w-[200px]">
          Click a ticker or "Simulate →" from an AI pick to view its chart
        </p>
      </div>
    );
  }
  return (
    <StockChart
      ticker={ticker.toUpperCase()}
      price={quote?.price}
      changePct={quote?.change_pct}
    />
  );
}


// ─── Recurring Investment Plans ───────────────────────────────────────────────

function RecurringView({ defaultTicker, onStateChange }: { defaultTicker: string; onStateChange: () => void }) {
  const [plans, setPlans] = useState<any[]>([]);
  const [plansLoading, setPlansLoading] = useState(true);
  const [addOpen, setAddOpen] = useState(false);

  // Form state
  const [ticker, setTicker] = useState(defaultTicker.toUpperCase());
  const [amount, setAmount] = useState("500");
  const [frequency, setFrequency] = useState("monthly");
  const [startDate, setStartDate] = useState(() => {
    const d = new Date();
    d.setFullYear(d.getFullYear() - 1);
    return d.toISOString().slice(0, 10);
  });
  const [submitting, setSubmitting] = useState(false);
  const [submitResult, setSubmitResult] = useState<any>(null);
  const [executing, setExecuting] = useState<number | null>(null);
  const [feedback, setFeedback] = useState<{ ok: boolean; msg: string } | null>(null);

  const today = new Date().toISOString().slice(0, 10);

  const loadPlans = useCallback(async () => {
    setPlansLoading(true);
    try {
      const data = await api.recurringPlans() as any[];
      setPlans(data ?? []);
    } catch { setPlans([]); }
    finally { setPlansLoading(false); }
  }, []);

  useEffect(() => { loadPlans(); }, [loadPlans]);

  const handleAdd = async () => {
    if (!ticker.trim() || !amount || parseFloat(amount) <= 0) {
      setFeedback({ ok: false, msg: "Enter a valid ticker and amount." }); return;
    }
    setSubmitting(true); setSubmitResult(null); setFeedback(null);
    try {
      const res = await api.recurringAdd({
        ticker: ticker.trim().toUpperCase(),
        amount: parseFloat(amount),
        frequency,
        start_date: startDate,
        backfill: false,
      }) as any;
      setPlans(res.plans ?? []);
      setSubmitResult(res.backfill);
      if (!res.backfill || res.backfill.ok !== false) {
        setAddOpen(false);
        setFeedback({ ok: true, msg: "Plan added successfully." });
        onStateChange();
      }
    } catch (e) {
      setFeedback({ ok: false, msg: e instanceof Error ? e.message : "Failed to add plan" });
    } finally { setSubmitting(false); }
  };

  const handleExecute = async (plan: any) => {
    setExecuting(plan.id);
    try {
      // Fetch current price first
      const quote = await api.quote(plan.ticker) as any;
      const price = quote?.price;
      if (!price) { setFeedback({ ok: false, msg: `Could not fetch price for ${plan.ticker}` }); return; }
      const res = await api.recurringExecute(plan.id, price, plan.name || plan.ticker) as any;
      if (res.ok !== false) {
        setFeedback({ ok: true, msg: `Bought ${res.shares_bought != null ? res.shares_bought.toFixed(4) : "N/A"} shares of ${plan.ticker} @ ${formatPrice(res.price)}` });
        await loadPlans();
        onStateChange();
      } else {
        setFeedback({ ok: false, msg: res.detail ?? "Execute failed" });
      }
    } catch (e) {
      setFeedback({ ok: false, msg: e instanceof Error ? e.message : "Execute failed" });
    } finally { setExecuting(null); }
  };

  const handleDelete = async (planId: number) => {
    if (!confirm("Remove this recurring plan?")) return;
    await api.recurringDelete(planId);
    setPlans((p) => p.filter((x) => x.id !== planId));
  };

  const freqLabel = (f: string) =>
    f === "weekly" ? "weekly" : f === "biweekly" ? "bi-weekly" : "monthly";

  return (
    <div className="space-y-4">
      {/* Active Plans */}
      <Card title="Recurring Investment Plans" titleRight={
        <button
          onClick={() => setAddOpen((o) => !o)}
          className="flex items-center gap-1 text-xs bg-cyan-600/20 border border-cyan-600/30 text-cyan-400 hover:bg-cyan-600/30 px-2.5 py-1 rounded-lg transition-colors"
        >
          <PlusCircle size={11} /> New Plan
        </button>
      }>
        {/* Feedback */}
        {feedback && (
          <div className={`flex items-start gap-2 text-sm rounded-lg px-3 py-2 mb-3 ${feedback.ok ? "bg-emerald-500/10 text-emerald-400" : "bg-red-500/10 text-red-400"}`}>
            {feedback.ok ? <CheckCircle2 size={14} className="shrink-0 mt-0.5" /> : <AlertCircle size={14} className="shrink-0 mt-0.5" />}
            {feedback.msg}
          </div>
        )}

        {plansLoading && <div className="text-xs text-zinc-500 py-4 text-center">Loading plans…</div>}

        {!plansLoading && plans.length === 0 && !addOpen && (
          <div className="flex flex-col items-center py-10 text-zinc-600">
            <Repeat2 size={28} className="mb-2 opacity-30" />
            <p className="text-sm mb-3">No recurring plans yet.</p>
            <button onClick={() => setAddOpen(true)} className="text-xs text-cyan-400 hover:underline">
              + Add your first plan
            </button>
          </div>
        )}

        {plans.length > 0 && (
          <div className="space-y-2 mb-3">
            {plans.map((plan) => (
              <div key={plan.id} className={`rounded-xl border p-3 ${plan.is_due ? "border-emerald-800/50 bg-emerald-950/10" : "border-zinc-800"}`}>
                <div className="flex items-center justify-between gap-2">
                  <div className="flex items-center gap-2 min-w-0">
                    <span className="font-bold text-cyan-400 text-sm shrink-0">{plan.ticker}</span>
                    <span className="text-xs text-zinc-400 shrink-0">${formatNum(plan.amount, 0)} / {freqLabel(plan.frequency)}</span>
                    {plan.is_due && (
                      <span className="text-[10px] bg-emerald-500/15 border border-emerald-600/30 text-emerald-400 px-1.5 py-0.5 rounded shrink-0">DUE</span>
                    )}
                  </div>
                  <div className="flex items-center gap-2 shrink-0">
                    {plan.is_due && (
                      <button
                        onClick={() => handleExecute(plan)}
                        disabled={executing === plan.id}
                        className="flex items-center gap-1 text-xs bg-emerald-600/20 border border-emerald-600/30 text-emerald-400 hover:bg-emerald-600/30 px-2 py-1 rounded-lg transition-colors disabled:opacity-40"
                      >
                        <Play size={10} /> {executing === plan.id ? "Buying…" : "Execute"}
                      </button>
                    )}
                    <button onClick={() => handleDelete(plan.id)} className="text-zinc-600 hover:text-red-400 transition-colors p-1">
                      <Trash2 size={12} />
                    </button>
                  </div>
                </div>
                <div className="grid grid-cols-3 gap-2 mt-2 text-[10px] text-zinc-500">
                  <div>
                    <div className="text-zinc-600 mb-0.5">Total invested</div>
                    <div className="text-zinc-300 font-medium">${formatNum(plan.total_invested, 0)}</div>
                  </div>
                  <div>
                    <div className="text-zinc-600 mb-0.5">Executions</div>
                    <div className="text-zinc-300 font-medium">{plan.num_executions}</div>
                  </div>
                  <div>
                    <div className="text-zinc-600 mb-0.5">{plan.is_due ? "⚡ Due now" : "Next buy"}</div>
                    <div className={plan.is_due ? "text-emerald-400 font-medium" : "text-zinc-300 font-medium"}>
                      {plan.next_due_date}
                    </div>
                  </div>
                </div>
              </div>
            ))}
          </div>
        )}

        {/* Add Plan form */}
        {addOpen && (
          <div className="border border-zinc-700 rounded-xl p-4 space-y-3 bg-zinc-800/30">
            <div className="text-xs font-semibold text-zinc-300 mb-1">New Recurring Plan</div>
            <div className="grid grid-cols-2 gap-2">
              <div>
                <label className="text-xs text-zinc-500 block mb-1">Ticker</label>
                <input type="text" value={ticker} onChange={(e) => setTicker(e.target.value.toUpperCase())} maxLength={10}
                  className="w-full bg-zinc-800 border border-zinc-700 rounded-lg px-3 py-2 text-sm text-zinc-100 focus:outline-none focus:border-cyan-500" />
              </div>
              <div>
                <label className="text-xs text-zinc-500 block mb-1">Frequency</label>
                <select value={frequency} onChange={(e) => setFrequency(e.target.value)}
                  className="w-full bg-zinc-800 border border-zinc-700 rounded-lg px-3 py-2 text-sm text-zinc-100 focus:outline-none focus:border-cyan-500">
                  <option value="monthly">Monthly</option>
                  <option value="biweekly">Bi-weekly</option>
                  <option value="weekly">Weekly</option>
                </select>
              </div>
            </div>
            <div className="grid grid-cols-2 gap-2">
              <div>
                <label className="text-xs text-zinc-500 block mb-1">Amount per buy ($)</label>
                <input type="number" min="1" step="50" value={amount} onChange={(e) => setAmount(e.target.value)}
                  className="w-full bg-zinc-800 border border-zinc-700 rounded-lg px-3 py-2 text-sm text-zinc-100 focus:outline-none focus:border-cyan-500" />
              </div>
              <div>
                <label className="text-xs text-zinc-500 block mb-1">Start date</label>
                <input type="date" value={startDate} max={today} onChange={(e) => setStartDate(e.target.value)}
                  className="w-full bg-zinc-800 border border-zinc-700 rounded-lg px-3 py-2 text-sm text-zinc-100 focus:outline-none focus:border-cyan-500" />
              </div>
            </div>

            <div className="flex gap-2 pt-1">
              <button
                onClick={handleAdd}
                disabled={submitting}
                className="flex-1 py-2 bg-cyan-600/20 border border-cyan-600/30 text-cyan-400 rounded-lg text-sm font-medium hover:bg-cyan-600/30 transition-colors disabled:opacity-40"
              >
                {submitting ? "Adding…" : "Add Plan"}
              </button>
              <button onClick={() => setAddOpen(false)} className="px-4 py-2 text-sm text-zinc-500 hover:text-zinc-300 transition-colors">
                Cancel
              </button>
            </div>

            {submitResult?.ok === false && (
              <div className="text-xs text-red-400 flex items-center gap-1">
                <AlertCircle size={11} /> {submitResult.error}
              </div>
            )}
          </div>
        )}
      </Card>

      <p className="text-[10px] text-zinc-700 italic px-1">
        Recurring plans execute at live prices when you click Execute. Backfill uses real historical adjusted closing prices. This is a paper trading simulator — not real money.
      </p>
    </div>
  );
}

