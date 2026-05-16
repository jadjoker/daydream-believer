import { type ClassValue, clsx } from "clsx";
import { twMerge } from "tailwind-merge";

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
}

export function formatNum(n: number | null | undefined, decimals = 2): string {
  if (n == null || isNaN(n)) return "—";
  return n.toLocaleString("en-US", { maximumFractionDigits: decimals });
}

export function formatPct(n: number | null | undefined, decimals = 2): string {
  if (n == null || isNaN(n)) return "—";
  const sign = n > 0 ? "+" : "";
  return `${sign}${n.toFixed(decimals)}%`;
}

export function formatMarketCap(n: number | null | undefined): string {
  if (n == null || isNaN(n)) return "—";
  if (n >= 1e12) return `$${(n / 1e12).toFixed(2)}T`;
  if (n >= 1e9) return `$${(n / 1e9).toFixed(2)}B`;
  if (n >= 1e6) return `$${(n / 1e6).toFixed(2)}M`;
  return `$${n.toFixed(0)}`;
}

export function formatVolume(n: number | null | undefined): string {
  if (n == null || isNaN(n)) return "—";
  if (n >= 1e9) return `${(n / 1e9).toFixed(2)}B`;
  if (n >= 1e6) return `${(n / 1e6).toFixed(2)}M`;
  if (n >= 1e3) return `${(n / 1e3).toFixed(1)}K`;
  return n.toString();
}

export function formatPrice(n: number | null | undefined): string {
  if (n == null || isNaN(n)) return "—";
  return `$${n.toFixed(2)}`;
}

export function colorClass(value: number | null | undefined): string {
  if (value == null) return "text-zinc-400";
  if (value > 0) return "text-emerald-400";
  if (value < 0) return "text-red-400";
  return "text-zinc-400";
}

export function rsiColor(rsi: number | null | undefined): string {
  if (rsi == null) return "text-zinc-400";
  if (rsi >= 70) return "text-red-400";
  if (rsi <= 30) return "text-emerald-400";
  return "text-yellow-400";
}

export function sentimentColor(label: string): string {
  const l = label?.toLowerCase();
  if (l === "bullish") return "text-emerald-400";
  if (l === "bearish") return "text-red-400";
  return "text-yellow-400";
}

export function sentimentBg(label: string): string {
  const l = label?.toLowerCase();
  if (l === "bullish") return "bg-emerald-500/20 border-emerald-500/40 text-emerald-400";
  if (l === "bearish") return "bg-red-500/20 border-red-500/40 text-red-400";
  return "bg-yellow-500/20 border-yellow-500/40 text-yellow-400";
}
