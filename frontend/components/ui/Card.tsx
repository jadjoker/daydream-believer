"use client";
import { cn } from "@/lib/utils";

interface CardProps {
  children: React.ReactNode;
  className?: string;
  title?: string;
  titleRight?: React.ReactNode;
}

export function Card({ children, className, title, titleRight }: CardProps) {
  return (
    <div className={cn("bg-zinc-900 border border-zinc-800 rounded-xl", className)}>
      {title && (
        <div className="flex items-center justify-between px-4 py-3 border-b border-zinc-800">
          <span className="text-xs font-semibold text-zinc-400 uppercase tracking-wider">{title}</span>
          {titleRight && <div className="text-xs text-zinc-500">{titleRight}</div>}
        </div>
      )}
      <div className="p-4">{children}</div>
    </div>
  );
}

export function StatCard({
  label,
  value,
  sub,
  valueClass,
}: {
  label: string;
  value: React.ReactNode;
  sub?: React.ReactNode;
  valueClass?: string;
}) {
  return (
    <div className="bg-zinc-900/60 border border-zinc-800 rounded-lg p-3">
      <div className="text-xs text-zinc-500 mb-1">{label}</div>
      <div className={cn("text-base font-semibold tabular-nums", valueClass)}>{value}</div>
      {sub && <div className="text-xs text-zinc-500 mt-0.5">{sub}</div>}
    </div>
  );
}
