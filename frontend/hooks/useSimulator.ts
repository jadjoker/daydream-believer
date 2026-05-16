"use client";
import { useState, useCallback, useEffect } from "react";
import { api } from "@/lib/api";

export interface Trade {
  id: string;
  ticker: string;
  name: string;
  action: "buy" | "sell";
  shares: number;
  price: number;
  total: number;
  timestamp: string;
  thesis: string;
  closePrice?: number;
  closeTimestamp?: string;
  realizedPnl?: number;
  realizedPnlPct?: number;
  outcome?: "win" | "loss" | "breakeven";
}

export interface Position {
  ticker: string;
  name: string;
  shares: number;
  avgCost: number;
  openTradeIds: string[];
}

export interface SimulatorState {
  cash: number;
  startingBalance: number;
  positions: Record<string, Position>;
  trades: Trade[];
}

const EMPTY: SimulatorState = { cash: 100_000, startingBalance: 100_000, positions: {}, trades: [] };

export function useSimulator() {
  const [state, setState] = useState<SimulatorState>(EMPTY);
  const [loading, setLoading] = useState(true);

  // Load shared state from backend on mount
  useEffect(() => {
    (api.simulatorState() as Promise<SimulatorState>)
      .then(setState)
      .catch(() => {})
      .finally(() => setLoading(false));
  }, []);

  const buy = useCallback(async (
    ticker: string, name: string, shares: number, price: number, thesis: string,
  ): Promise<{ ok: boolean; error?: string }> => {
    try {
      const next = await api.simulatorBuy({ ticker, name, shares, price, thesis }) as SimulatorState;
      setState(next);
      return { ok: true };
    } catch (e: any) {
      const msg = e?.message ?? "Buy failed";
      // Backend sends 400 with detail message
      const detail = msg.match(/400.*?([^:]+)$/)?.[1]?.trim() ?? msg;
      return { ok: false, error: detail };
    }
  }, []);

  const sell = useCallback(async (
    ticker: string, name: string, shares: number, price: number, thesis: string,
  ): Promise<{ ok: boolean; error?: string }> => {
    try {
      const next = await api.simulatorSell({ ticker, name, shares, price, thesis }) as SimulatorState;
      setState(next);
      return { ok: true };
    } catch (e: any) {
      const msg = e?.message ?? "Sell failed";
      const detail = msg.match(/400.*?([^:]+)$/)?.[1]?.trim() ?? msg;
      return { ok: false, error: detail };
    }
  }, []);

  const addFunds = useCallback(async (amount: number) => {
    try {
      const next = await api.simulatorAddFunds(amount) as SimulatorState;
      setState(next);
    } catch {}
  }, []);

  const reset = useCallback(async () => {
    try {
      const next = await api.simulatorReset() as SimulatorState;
      setState(next);
    } catch {}
  }, []);

  const refetch = useCallback(async () => {
    try {
      const next = await api.simulatorState() as SimulatorState;
      setState(next);
    } catch {}
  }, []);

  const closedTrades = state.trades.filter((t) => t.action === "sell");
  const wins = closedTrades.filter((t) => t.outcome === "win").length;
  const losses = closedTrades.filter((t) => t.outcome === "loss").length;
  const winRate = closedTrades.length > 0 ? (wins / closedTrades.length) * 100 : 0;
  const totalRealizedPnl = closedTrades.reduce((s, t) => s + (t.realizedPnl ?? 0), 0);
  const avgWinPct = wins > 0
    ? closedTrades.filter((t) => t.outcome === "win").reduce((s, t) => s + (t.realizedPnlPct ?? 0), 0) / wins : 0;
  const avgLossPct = losses > 0
    ? closedTrades.filter((t) => t.outcome === "loss").reduce((s, t) => s + (t.realizedPnlPct ?? 0), 0) / losses : 0;

  return {
    state,
    loading,
    buy,
    sell,
    addFunds,
    reset,
    refetch,
    stats: { wins, losses, winRate, totalRealizedPnl, avgWinPct, avgLossPct, totalTrades: closedTrades.length },
  };
}
