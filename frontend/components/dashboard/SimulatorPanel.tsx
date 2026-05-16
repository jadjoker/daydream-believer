"use client";
import { useState, useCallback, useEffect } from "react";
import { useSimulator } from "@/hooks/useSimulator";
import { useData } from "@/hooks/useData";
import { api } from "@/lib/api";
import {
  formatNum, formatPct, formatPrice, formatMarketCap, colorClass,
} from "@/lib/utils";
import { Card, StatCard } from "@/components/ui/Card";
import { Badge } from "@/components/ui/Badge";
import {
  TrendingUp, TrendingDown, DollarSign, Target, RefreshCw,
  PlusCircle, History, BarChart2, AlertCircle, CheckCircle2, XCircle,
  CalendarDays, Repeat2, Trash2, Play, TrendingUp as ForecastIcon,
} from "lucide-react";

interface SimulatorPanelProps {
  ticker: string;
}

type View = "trade" | "portfolio" | "history" | "accuracy" | "dca" | "recurring";

export default function SimulatorPanel({ ticker }: SimulatorPanelProps) {
  const { state, loading, buy, sell, addFunds, reset, refetch, stats } = useSimulator();
  const [view, setView] = useState<View>("trade");

  const { data: quote } = useData(
    () => api.quote(ticker) as Promise<any>,
    [ticker],
    { refreshInterval: 30000 }
  );

  const currentPrice = quote?.price ?? 0;
  const positionsValue = Object.entries(state.positions).reduce(
    (sum, [, pos]) => sum + pos.shares * currentPrice,
    0
  );
  const totalValue = state.cash + positionsValue;
  const totalReturn = totalValue - state.startingBalance;
  const totalReturnPct = (totalReturn / state.startingBalance) * 100;

  const VIEWS: { id: View; label: string; icon: React.ReactNode }[] = [
    { id: "trade", label: "Trade", icon: <DollarSign size={13} /> },
    { id: "portfolio", label: "Portfolio", icon: <BarChart2 size={13} /> },
    { id: "history", label: "History", icon: <History size={13} /> },
    { id: "accuracy", label: "Accuracy", icon: <Target size={13} /> },
    { id: "dca", label: "DCA", icon: <CalendarDays size={13} /> },
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

      {/* View tabs */}
      <div className="flex gap-1">
        {VIEWS.map((v) => (
          <button
            key={v.id}
            onClick={() => setView(v.id)}
            className={`flex items-center gap-1.5 px-4 py-2 rounded-lg text-sm font-medium transition-colors ${
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
        <PortfolioView positions={state.positions} currentPrice={currentPrice} ticker={ticker} />
      )}
      {view === "history" && (
        <HistoryView trades={state.trades} />
      )}
      {view === "accuracy" && (
        <AccuracyView stats={stats} trades={state.trades} />
      )}
      {view === "dca" && (
        <DCAView defaultTicker={ticker} />
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
  const [action, setAction] = useState<"buy" | "sell">("buy");
  const [shares, setShares] = useState("");
  const [stopLoss, setStopLoss] = useState("");
  const [takeProfit, setTakeProfit] = useState("");
  const [maxRiskDollars, setMaxRiskDollars] = useState("");
  const [thesis, setThesis] = useState("");
  const [feedback, setFeedback] = useState<{ ok: boolean; msg: string } | null>(null);

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
    setFeedback(null);
    if (!sharesNum || sharesNum <= 0) {
      setFeedback({ ok: false, msg: "Enter a valid number of shares." });
      return;
    }
    const name = quote?.name || ticker;
    const fullThesis = [
      thesis,
      stopNum ? `SL: ${formatPrice(stopNum)}` : "",
      tpNum ? `TP: ${formatPrice(tpNum)}` : "",
    ].filter(Boolean).join(" | ");

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
  }, [action, sharesNum, currentPrice, ticker, thesis, stopNum, tpNum, buy, sell, quote]);

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
            onClick={() => { handleSubmit(); }}
            disabled={!sharesNum || sharesNum <= 0 || !currentPrice}
            className={`w-full py-2.5 rounded-xl font-semibold text-sm transition-colors disabled:opacity-40 disabled:cursor-not-allowed ${
              action === "buy"
                ? "bg-emerald-600 hover:bg-emerald-500 text-white"
                : "bg-red-600 hover:bg-red-500 text-white"
            }`}
          >
            {action === "buy" ? "Buy" : "Sell"} {sharesNum > 0 ? `${sharesNum} shares` : ""} of {ticker.toUpperCase()}
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

function PortfolioView({ positions, currentPrice, ticker }: { positions: any; currentPrice: number; ticker: string }) {
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
              const price = sym === ticker.toUpperCase() ? currentPrice : 0;
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

// ─── DCA View (Historical backtest + Compound Forecast toggle) ────────────────

type DCAFreq = "weekly" | "biweekly" | "monthly" | "none";

function DCAView({ defaultTicker }: { defaultTicker: string }) {
  const [dcaMode, setDcaMode] = useState<"historical" | "forecast">("historical");
  return (
    <div className="space-y-4">
      <div className="flex gap-1">
        {(["historical", "forecast"] as const).map((m) => (
          <button
            key={m}
            onClick={() => setDcaMode(m)}
            className={`px-4 py-1.5 rounded-lg text-sm font-medium transition-colors ${
              dcaMode === m
                ? "bg-zinc-800 text-zinc-100 border border-zinc-700"
                : "text-zinc-500 hover:text-zinc-300"
            }`}
          >
            {m === "historical" ? "Historical Backtest" : "Compound Forecast"}
          </button>
        ))}
      </div>
      {dcaMode === "historical" ? (
        <DCAHistoricalView defaultTicker={defaultTicker} />
      ) : (
        <CompoundForecastView defaultTicker={defaultTicker} />
      )}
    </div>
  );
}

function DCAHistoricalView({ defaultTicker }: { defaultTicker: string }) {
  const today = new Date().toISOString().slice(0, 10);
  const fiveYearsAgo = new Date(Date.now() - 5 * 365.25 * 24 * 3600 * 1000).toISOString().slice(0, 10);

  const [ticker, setTicker] = useState(defaultTicker.toUpperCase());
  const [start, setStart] = useState(fiveYearsAgo);
  const [end, setEnd] = useState(today);
  const [initial, setInitial] = useState("10000");
  const [recurring, setRecurring] = useState("500");
  const [frequency, setFrequency] = useState<DCAFreq>("monthly");
  const [result, setResult] = useState<any>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const handleRun = async () => {
    setError(null);
    // Client-side validation
    if (!ticker.trim()) { setError("Enter a ticker symbol."); return; }
    if (!start || !end) { setError("Select start and end dates."); return; }
    if (start >= end) { setError("Start date must be before end date."); return; }
    const todayCheck = new Date().toISOString().slice(0, 10);
    if (end > todayCheck) { setError("End date cannot be in the future — historical data only."); return; }
    const startDate = new Date(start);
    const endDate = new Date(end);
    const daysDiff = (endDate.getTime() - startDate.getTime()) / (1000 * 60 * 60 * 24);
    if (daysDiff < 30) { setError("Date range must be at least 30 days to produce meaningful results."); return; }
    const initVal = parseFloat(initial) || 0;
    if (initVal <= 0) { setError("Initial investment must be greater than $0."); return; }

    setLoading(true);
    setResult(null);
    try {
      const res = await api.simulatorDca({
        ticker: ticker.trim().toUpperCase(),
        start,
        end,
        initial: initVal,
        recurring: parseFloat(recurring) || 0,
        frequency,
      }) as any;
      setResult(res);
    } catch (e) {
      setError(e instanceof Error ? e.message : "DCA simulation failed");
    } finally {
      setLoading(false);
    }
  };

  const beat = result ? result.total_return_pct > result.spy_return_pct : false;

  return (
    <div className="space-y-4">
      <Card title="DCA Return Estimator">
        <div className="space-y-3">
          <div className="grid grid-cols-2 gap-2">
            <div>
              <label className="text-xs text-zinc-500 block mb-1">Ticker</label>
              <input
                type="text"
                value={ticker}
                onChange={(e) => setTicker(e.target.value.toUpperCase())}
                maxLength={10}
                className="w-full bg-zinc-800 border border-zinc-700 rounded-lg px-3 py-2 text-sm text-zinc-100 focus:outline-none focus:border-cyan-500"
              />
            </div>
            <div>
              <label className="text-xs text-zinc-500 block mb-1">Frequency</label>
              <select
                value={frequency}
                onChange={(e) => setFrequency(e.target.value as DCAFreq)}
                className="w-full bg-zinc-800 border border-zinc-700 rounded-lg px-3 py-2 text-sm text-zinc-100 focus:outline-none focus:border-cyan-500"
              >
                <option value="monthly">Monthly</option>
                <option value="biweekly">Bi-weekly</option>
                <option value="weekly">Weekly</option>
                <option value="none">One-time only</option>
              </select>
            </div>
          </div>

          <div className="grid grid-cols-2 gap-2">
            <div>
              <label className="text-xs text-zinc-500 block mb-1">Start Date</label>
              <input
                type="date"
                value={start}
                onChange={(e) => setStart(e.target.value)}
                max={end}
                className="w-full bg-zinc-800 border border-zinc-700 rounded-lg px-3 py-2 text-sm text-zinc-100 focus:outline-none focus:border-cyan-500"
              />
            </div>
            <div>
              <label className="text-xs text-zinc-500 block mb-1">End Date</label>
              <input
                type="date"
                value={end}
                onChange={(e) => setEnd(e.target.value)}
                min={start}
                max={today}
                className="w-full bg-zinc-800 border border-zinc-700 rounded-lg px-3 py-2 text-sm text-zinc-100 focus:outline-none focus:border-cyan-500"
              />
            </div>
          </div>

          <div className="grid grid-cols-2 gap-2">
            <div>
              <label className="text-xs text-zinc-500 block mb-1">Initial ($)</label>
              <input
                type="number"
                min="0"
                step="500"
                value={initial}
                onChange={(e) => setInitial(e.target.value)}
                className="w-full bg-zinc-800 border border-zinc-700 rounded-lg px-3 py-2 text-sm text-zinc-100 focus:outline-none focus:border-cyan-500"
              />
            </div>
            <div>
              <label className="text-xs text-zinc-500 block mb-1">
                Recurring ($){frequency !== "none" && <span className="text-zinc-600 ml-1">per {frequency.replace("ly", "")}</span>}
              </label>
              <input
                type="number"
                min="0"
                step="100"
                value={recurring}
                onChange={(e) => setRecurring(e.target.value)}
                disabled={frequency === "none"}
                className="w-full bg-zinc-800 border border-zinc-700 rounded-lg px-3 py-2 text-sm text-zinc-100 focus:outline-none focus:border-cyan-500 disabled:opacity-40"
              />
            </div>
          </div>

          <button
            onClick={handleRun}
            disabled={loading || !ticker.trim()}
            className="w-full py-2.5 bg-cyan-600/20 border border-cyan-600/30 text-cyan-400 rounded-xl font-semibold text-sm hover:bg-cyan-600/30 transition-colors disabled:opacity-40 active:bg-cyan-600/40"
          >
            {loading ? "Running simulation…" : "Run DCA Simulation"}
          </button>

          {error && (
            <div className="flex items-start gap-2 text-sm text-red-400 bg-red-500/10 rounded-lg px-3 py-2.5">
              <AlertCircle size={14} className="shrink-0 mt-0.5" />
              {error}
            </div>
          )}
        </div>
      </Card>

      {result && !loading && (
        <>
          <Card title={`${result.ticker} Results`} titleRight={
            <span className={`text-xs font-semibold ${beat ? "text-emerald-400" : "text-red-400"}`}>
              {beat ? "✓ Beat SPY" : "✗ Underperformed SPY"}
            </span>
          }>
            <div className="grid grid-cols-2 gap-3 mb-4">
              <StatCard
                label="Final Value"
                value={`$${formatNum(result.final_value, 2)}`}
                valueClass={colorClass(result.total_return_dollars)}
                sub={`${result.total_return_dollars >= 0 ? "+" : ""}$${formatNum(result.total_return_dollars, 2)}`}
              />
              <StatCard
                label="Total Return"
                value={formatPct(result.total_return_pct)}
                valueClass={colorClass(result.total_return_pct)}
              />
              <StatCard
                label="Total Invested"
                value={`$${formatNum(result.total_invested, 2)}`}
                valueClass="text-zinc-300"
                sub={`${result.num_purchases} purchases`}
              />
              <StatCard
                label="Max Drawdown"
                value={`-${result.max_drawdown_pct.toFixed(1)}%`}
                valueClass="text-red-400"
              />
            </div>

            <div className="bg-zinc-800/50 rounded-lg p-3 space-y-2">
              <div className="text-xs text-zinc-500 uppercase tracking-wider mb-2">vs SPY (same cash flows)</div>
              <div className="flex items-center justify-between text-sm">
                <span className="text-zinc-400">{result.ticker}</span>
                <span className={`font-bold tabular-nums ${colorClass(result.total_return_pct)}`}>
                  {formatPct(result.total_return_pct)} &rarr; ${formatNum(result.final_value, 0)}
                </span>
              </div>
              <div className="flex items-center justify-between text-sm">
                <span className="text-zinc-400">SPY</span>
                <span className={`font-bold tabular-nums ${colorClass(result.spy_return_pct)}`}>
                  {formatPct(result.spy_return_pct)} &rarr; ${formatNum(result.spy_final_value, 0)}
                </span>
              </div>
              <div className="space-y-1 pt-1">
                {[
                  { label: result.ticker, pct: result.total_return_pct, color: "bg-cyan-500" },
                  { label: "SPY", pct: result.spy_return_pct, color: "bg-amber-500" },
                ].map(({ label, pct, color }) => {
                  const maxAbs = Math.max(Math.abs(result.total_return_pct), Math.abs(result.spy_return_pct), 1);
                  const w = Math.min(100, (Math.abs(pct) / maxAbs) * 100);
                  return (
                    <div key={label}>
                      <div className="flex justify-between text-[10px] text-zinc-600 mb-0.5">
                        <span>{label}</span><span>{formatPct(pct)}</span>
                      </div>
                      <div className="h-2 bg-zinc-700 rounded-full overflow-hidden">
                        <div className={`h-full rounded-full ${pct >= 0 ? color : "bg-red-500"}`} style={{ width: `${w}%` }} />
                      </div>
                    </div>
                  );
                })}
              </div>
            </div>

            <p className="text-[10px] text-zinc-600 italic mt-3">
              Uses adjusted closing prices. Past performance ≠ future results. Not financial advice.
            </p>
          </Card>

          {result.series?.length > 1 && (
            <Card title="Growth Chart">
              <MiniChart series={result.series} spySeries={result.spy_series} ticker={result.ticker} />
            </Card>
          )}
        </>
      )}
    </div>
  );
}

// ─── Compound Forecast View ───────────────────────────────────────────────────

function CompoundForecastView({ defaultTicker }: { defaultTicker: string }) {
  const [initial, setInitial] = useState("10000");
  const [monthly, setMonthly] = useState("500");
  const [years, setYears] = useState("10");
  const [customRate, setCustomRate] = useState("");

  const P = Math.max(0, parseFloat(initial) || 0);
  const PMT = Math.max(0, parseFloat(monthly) || 0);
  const N = Math.max(1, Math.min(50, parseInt(years) || 10));
  const numMonths = N * 12;

  const SCENARIOS = [
    { label: "Conservative", rate: 0.05, color: "#f59e0b", textCls: "text-amber-400" },
    { label: "Moderate",     rate: 0.08, color: "#22d3ee", textCls: "text-cyan-400" },
    { label: "Aggressive",   rate: 0.12, color: "#10b981", textCls: "text-emerald-400" },
  ];
  const customRateNum = parseFloat(customRate);
  const scenarios = customRate && !isNaN(customRateNum) && customRateNum > 0
    ? [...SCENARIOS, { label: "Custom", rate: customRateNum / 100, color: "#a78bfa", textCls: "text-violet-400" }]
    : SCENARIOS;

  function generateSeries(annualRate: number) {
    const r = annualRate / 12;
    const data: { month: number; value: number; invested: number }[] = [];
    let value = P;
    let invested = P;
    for (let m = 0; m <= numMonths; m++) {
      if (m > 0) {
        value = value * (1 + r) + PMT;
        invested += PMT;
      }
      data.push({ month: m, value: Math.round(value), invested: Math.round(invested) });
    }
    return data;
  }

  const seriesData = scenarios.map((s) => ({ ...s, data: generateSeries(s.rate) }));
  const totalInvested = P + PMT * numMonths;

  // SVG chart
  const W = 400; const H = 130; const PAD = 10;
  const allVals = seriesData.flatMap((s) => s.data.map((d) => d.value));
  const maxV = Math.max(...allVals, totalInvested, 1);
  const minV = 0;
  const range = maxV - minV;
  const toX = (m: number) => PAD + (m / numMonths) * (W - PAD * 2);
  const toY = (v: number) => H - PAD - ((v - minV) / range) * (H - PAD * 2);
  const makePath = (data: typeof seriesData[0]["data"]) =>
    data.map((d, i) => `${i === 0 ? "M" : "L"} ${toX(d.month).toFixed(1)} ${toY(d.value).toFixed(1)}`).join(" ");
  const investedPath = seriesData[0].data
    .map((d, i) => `${i === 0 ? "M" : "L"} ${toX(d.month).toFixed(1)} ${toY(d.invested).toFixed(1)}`)
    .join(" ");

  return (
    <div className="space-y-4">
      <Card title="Compound Growth Forecast">
        <div className="text-xs text-zinc-500 mb-3 leading-relaxed">
          Projects future portfolio value using a fixed annual return rate. Not a prediction — use this to visualize how consistent investing compounds over time.
        </div>
        <div className="space-y-3">
          <div className="grid grid-cols-3 gap-2">
            <div>
              <label className="text-xs text-zinc-500 block mb-1">Initial ($)</label>
              <input type="number" min="0" step="1000" value={initial}
                onChange={(e) => setInitial(e.target.value)}
                className="w-full bg-zinc-800 border border-zinc-700 rounded-lg px-3 py-2 text-sm text-zinc-100 focus:outline-none focus:border-cyan-500" />
            </div>
            <div>
              <label className="text-xs text-zinc-500 block mb-1">Monthly ($)</label>
              <input type="number" min="0" step="100" value={monthly}
                onChange={(e) => setMonthly(e.target.value)}
                className="w-full bg-zinc-800 border border-zinc-700 rounded-lg px-3 py-2 text-sm text-zinc-100 focus:outline-none focus:border-cyan-500" />
            </div>
            <div>
              <label className="text-xs text-zinc-500 block mb-1">Years</label>
              <input type="number" min="1" max="50" step="1" value={years}
                onChange={(e) => setYears(e.target.value)}
                className="w-full bg-zinc-800 border border-zinc-700 rounded-lg px-3 py-2 text-sm text-zinc-100 focus:outline-none focus:border-cyan-500" />
            </div>
          </div>
          <div>
            <label className="text-xs text-zinc-500 block mb-1">Custom annual return % (optional)</label>
            <input type="number" min="0" max="100" step="0.5" placeholder="e.g. 15" value={customRate}
              onChange={(e) => setCustomRate(e.target.value)}
              className="w-full bg-zinc-800 border border-zinc-700 rounded-lg px-3 py-2 text-sm text-zinc-100 focus:outline-none focus:border-cyan-500" />
          </div>
        </div>
      </Card>

      <Card title={`${N}-Year Projections`} titleRight={
        <span className="text-xs text-zinc-600">Total invested: ${formatNum(totalInvested, 0)}</span>
      }>
        <div className="grid grid-cols-1 sm:grid-cols-3 gap-2 mb-4">
          {seriesData.map((s) => {
            const final = s.data[s.data.length - 1];
            const gain = final.value - final.invested;
            const gainPct = final.invested > 0 ? (gain / final.invested) * 100 : 0;
            return (
              <div key={s.label} className="bg-zinc-800/50 rounded-xl p-3 border border-zinc-700/40">
                <div className="text-[10px] text-zinc-500 uppercase tracking-wider mb-1">{s.label} ({(s.rate * 100).toFixed(0)}%/yr)</div>
                <div className={`text-xl font-bold tabular-nums ${s.textCls}`}>${formatNum(final.value, 0)}</div>
                <div className="text-xs text-zinc-500 mt-0.5">
                  +${formatNum(gain, 0)} gain · +{gainPct.toFixed(0)}%
                </div>
              </div>
            );
          })}
        </div>

        {/* SVG chart */}
        <div className="overflow-x-auto">
          <svg viewBox={`0 0 ${W} ${H + 28}`} className="w-full" style={{ minWidth: "260px" }}>
            <path d={investedPath} fill="none" stroke="#52525b" strokeWidth="1.2" strokeDasharray="3 2" />
            {seriesData.map((s) => (
              <path key={s.label} d={makePath(s.data)} fill="none" stroke={s.color} strokeWidth={s.label === "Moderate" ? 2 : 1.5} opacity="0.85" />
            ))}
            {/* Legend */}
            {seriesData.map((s, i) => {
              const final = s.data[s.data.length - 1];
              const x = PAD + i * ((W - PAD * 2) / seriesData.length);
              return (
                <g key={s.label}>
                  <circle cx={x + 4} cy={H + 11} r="3" fill={s.color} />
                  <text x={x + 10} y={H + 15} fill="#a1a1aa" fontSize="8.5">
                    {s.label} ${(final.value / 1000).toFixed(0)}K
                  </text>
                </g>
              );
            })}
            <line x1={W - 58} y1={H + 9} x2={W - 52} y2={H + 9} stroke="#52525b" strokeWidth="1.2" strokeDasharray="2 2" />
            <text x={W - 49} y={H + 14} fill="#71717a" fontSize="8.5">Invested ${(totalInvested / 1000).toFixed(0)}K</text>
          </svg>
        </div>

        <p className="text-[10px] text-zinc-600 italic mt-2">
          Assumes constant annual return, monthly compounding, contributions at start of each month. Past market returns don't guarantee future results.
        </p>
      </Card>
    </div>
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
  const [backfill, setBackfill] = useState(true);
  const [submitting, setSubmitting] = useState(false);
  const [submitResult, setSubmitResult] = useState<any>(null);
  const [executing, setExecuting] = useState<number | null>(null);
  const [feedback, setFeedback] = useState<{ ok: boolean; msg: string } | null>(null);

  const today = new Date().toISOString().slice(0, 10);
  const isPastStart = startDate < today;

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
        backfill: isPastStart && backfill,
      }) as any;
      setPlans(res.plans ?? []);
      setSubmitResult(res.backfill);
      if (!res.backfill || res.backfill.ok !== false) {
        setAddOpen(false);
        setFeedback({
          ok: true,
          msg: res.backfill?.ok
            ? `Plan added + ${res.backfill.num_executions} historical buys executed ($${formatNum(res.backfill.total_invested, 0)} invested).${res.backfill.cash_warning ? " ⚠ Cash went negative — add funds." : ""}`
            : "Plan added. No backfill data available.",
        });
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
        setFeedback({ ok: true, msg: `Bought ${res.shares_bought?.toFixed(4)} shares of ${plan.ticker} @ ${formatPrice(res.price)}` });
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

            {isPastStart && (
              <label className="flex items-start gap-2.5 cursor-pointer">
                <input type="checkbox" checked={backfill} onChange={(e) => setBackfill(e.target.checked)}
                  className="mt-0.5 accent-cyan-500" />
                <div>
                  <div className="text-xs text-zinc-300 font-medium">Backfill historical purchases</div>
                  <div className="text-[10px] text-zinc-500 mt-0.5">
                    Executes every {freqLabel(frequency)} buy from {startDate} to today at real historical prices. Adds shares to your portfolio with correct cost basis and deducts from your cash.
                  </div>
                </div>
              </label>
            )}

            <div className="flex gap-2 pt-1">
              <button
                onClick={handleAdd}
                disabled={submitting}
                className="flex-1 py-2 bg-cyan-600/20 border border-cyan-600/30 text-cyan-400 rounded-lg text-sm font-medium hover:bg-cyan-600/30 transition-colors disabled:opacity-40"
              >
                {submitting ? (backfill && isPastStart ? "Backfilling…" : "Adding…") : "Add Plan"}
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

function MiniChart({ series, spySeries, ticker }: { series: any[]; spySeries: any[]; ticker: string }) {
  const W = 400;
  const H = 120;
  const PAD = 8;

  const allVals = [...series.map((s: any) => s.value), ...spySeries.map((s: any) => s.value)];
  const minV = Math.min(...allVals, 0);
  const maxV = Math.max(...allVals, 1);
  const range = maxV - minV || 1;

  const toX = (i: number, total: number) => PAD + (i / Math.max(total - 1, 1)) * (W - PAD * 2);
  const toY = (v: number) => H - PAD - ((v - minV) / range) * (H - PAD * 2);

  const makePath = (data: any[]) =>
    data.map((row: any, i: number) =>
      `${i === 0 ? "M" : "L"} ${toX(i, data.length).toFixed(1)} ${toY(row.value).toFixed(1)}`
    ).join(" ");

  const investedPath = series.map((row: any, i: number) =>
    `${i === 0 ? "M" : "L"} ${toX(i, series.length).toFixed(1)} ${toY(row.invested).toFixed(1)}`
  ).join(" ");

  const lastTicker = series[series.length - 1];
  const lastSpy = spySeries[spySeries.length - 1];

  return (
    <div className="overflow-x-auto">
      <svg viewBox={`0 0 ${W} ${H + 22}`} className="w-full" style={{ minWidth: "260px" }}>
        <path d={investedPath} fill="none" stroke="#52525b" strokeWidth="1" strokeDasharray="3 2" />
        {spySeries.length > 1 && (
          <path d={makePath(spySeries)} fill="none" stroke="#f59e0b" strokeWidth="1.5" opacity="0.8" />
        )}
        <path d={makePath(series)} fill="none" stroke="#22d3ee" strokeWidth="2" />

        <circle cx={PAD + 4} cy={H + 11} r="3" fill="#22d3ee" />
        <text x={PAD + 10} y={H + 15} fill="#a1a1aa" fontSize="9">{ticker} ${(lastTicker.value / 1000).toFixed(1)}K</text>
        <circle cx={W / 2 - 10} cy={H + 11} r="3" fill="#f59e0b" />
        <text x={W / 2 - 4} y={H + 15} fill="#a1a1aa" fontSize="9">SPY ${((lastSpy?.value ?? 0) / 1000).toFixed(1)}K</text>
        <line x1={W - 52} y1={H + 9} x2={W - 46} y2={H + 9} stroke="#52525b" strokeWidth="1.2" strokeDasharray="2 2" />
        <text x={W - 43} y={H + 14} fill="#71717a" fontSize="9">Invested</text>
      </svg>
    </div>
  );
}
