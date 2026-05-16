import { cn } from "@/lib/utils";

interface BadgeProps {
  children: React.ReactNode;
  variant?: "bullish" | "bearish" | "neutral" | "info" | "warning" | "default";
  className?: string;
}

const variants = {
  bullish: "bg-emerald-500/15 text-emerald-400 border-emerald-500/30",
  bearish: "bg-red-500/15 text-red-400 border-red-500/30",
  neutral: "bg-yellow-500/15 text-yellow-400 border-yellow-500/30",
  info: "bg-cyan-500/15 text-cyan-400 border-cyan-500/30",
  warning: "bg-orange-500/15 text-orange-400 border-orange-500/30",
  default: "bg-zinc-800 text-zinc-300 border-zinc-700",
};

export function Badge({ children, variant = "default", className }: BadgeProps) {
  return (
    <span className={cn("inline-flex items-center px-2 py-0.5 rounded-md text-xs font-medium border", variants[variant], className)}>
      {children}
    </span>
  );
}
