import type { ReactNode } from "react";
import { motion } from "framer-motion";
import { Loader2 } from "lucide-react";

export function Card({ children, className = "", delay = 0 }: { children: ReactNode; className?: string; delay?: number }) {
  return <motion.section initial={{ opacity: 0, y: 14 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.35, delay }} className={`glass p-5 ${className}`}>{children}</motion.section>;
}
export const Spinner = ({ className = "h-4 w-4" }: { className?: string }) => <Loader2 className={`animate-spin ${className}`} />;
export function PageLoader() { return <div className="grid place-items-center py-24"><Spinner className="h-8 w-8 text-brand-500" /></div>; }
export function Skeleton({ className = "h-20" }: { className?: string }) {
  return <div className={`relative overflow-hidden rounded-2xl bg-slate-200/70 dark:bg-white/5 ${className}`}><div className="absolute inset-0 -translate-x-full animate-[shimmer_1.4s_infinite] bg-gradient-to-r from-transparent via-white/40 to-transparent dark:via-white/10" /></div>;
}
export function Pill({ tone = "mute", children }: { tone?: "good" | "warn" | "bad" | "mute" | "brand"; children: ReactNode }) {
  const t = { good: "bg-emerald-500/15 text-emerald-700 dark:text-emerald-300", warn: "bg-amber-500/15 text-amber-700 dark:text-amber-300",
    bad: "bg-rose-500/15 text-rose-700 dark:text-rose-300", mute: "bg-slate-500/15 text-slate-600 dark:text-slate-300", brand: "bg-brand-500/15 text-brand-600 dark:text-brand-300" }[tone];
  return <span className={`pill ${t}`}>{children}</span>;
}
export function ScoreRing({ score }: { score: number | null }) {
  if (score === null) return null;
  const r = 20, c = 2 * Math.PI * r, color = score >= 85 ? "#10b981" : score >= 70 ? "#6366f1" : "#f59e0b";
  return (
    <div className="relative grid h-14 w-14 shrink-0 place-items-center" aria-label={`Match score ${score}`}>
      <svg viewBox="0 0 48 48" className="h-14 w-14 -rotate-90"><circle cx="24" cy="24" r={r} fill="none" stroke="currentColor" strokeWidth="4" className="text-slate-200 dark:text-white/10" />
        <motion.circle cx="24" cy="24" r={r} fill="none" stroke={color} strokeWidth="4" strokeLinecap="round" strokeDasharray={c} initial={{ strokeDashoffset: c }} animate={{ strokeDashoffset: c * (1 - score / 100) }} transition={{ duration: 0.9 }} /></svg>
      <span className="absolute text-sm font-bold">{score}</span>
    </div>
  );
}
export function QuotaBadge({ remaining, max, company }: { remaining: number | null; max: number; company: string }) {
  if (remaining === null) return null;
  return <Pill tone={remaining <= 0 ? "bad" : remaining <= 1 ? "warn" : "good"}>{remaining} of {max} applications left at {company}</Pill>;
}
export function Empty({ title, body, action }: { title: string; body: string; action?: ReactNode }) {
  return <Card className="py-12 text-center"><p className="text-lg font-semibold">{title}</p><p className="mx-auto mt-1 max-w-sm text-sm text-slate-500">{body}</p>{action && <div className="mt-5">{action}</div>}</Card>;
}
