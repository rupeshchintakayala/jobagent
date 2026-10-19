import { useEffect, useRef, useState } from "react";
import { Link } from "react-router-dom";
import { motion } from "framer-motion";
import { ArrowRight, Check, KeyRound, Play, ShieldCheck, UserRound } from "lucide-react";
import { api } from "../lib/api";
import { useAuth } from "../lib/auth";
import { useToast } from "../lib/toast";
import { Card, Pill, Spinner } from "../components/ui";

function Step({ n, done, title, body, to, cta }: { n: number; done: boolean; title: string; body: string; to: string; cta: string }) {
  return (
    <li className="flex items-center gap-3 border-b border-slate-200 py-3 last:border-0 dark:border-white/10">
      <span className={`grid h-7 w-7 shrink-0 place-items-center rounded-full text-xs font-bold ${done ? "bg-emerald-500 text-white" : "bg-slate-200 dark:bg-white/10"}`}>{done ? <Check className="h-4 w-4" /> : n}</span>
      <div className="flex-1"><p className="font-semibold">{title}</p><p className="text-sm text-slate-500">{body}</p></div>
      {!done && <Link to={to} className="btn !px-3 !py-1.5">{cta}<ArrowRight className="h-4 w-4" /></Link>}
    </li>
  );
}

export default function Dashboard() {
  const { me, refresh } = useAuth();
  const toast = useToast();
  const [busy, setBusy] = useState(false);
  const timer = useRef<number>();

  // poll while a run is in progress
  useEffect(() => {
    if (me?.run?.state === "running") { timer.current = window.setInterval(() => void refresh(), 4000); }
    return () => window.clearInterval(timer.current);
  }, [me?.run?.state, refresh]);

  if (!me) return null;
  const ready = me.has_key && me.profile_confirmed;
  const running = me.run?.state === "running";
  const pct = Math.min(100, Math.round((100 * me.spent_eur) / (me.cap_eur || 1)));

  async function run() {
    setBusy(true);
    try { await api.run(); await refresh(); } catch (e) { toast("err", (e as Error).message); } finally { setBusy(false); }
  }

  const stats: [string, number, string][] = [["To review", me.counts.drafted, "drafted"], ["Approved", me.counts.approved, "approved"], ["Applied", me.counts.submitted, "submitted"], ["Rejected", me.counts.rejected, "rejected"]];

  return (
    <div className="space-y-4">
      {!ready && (
        <Card><h1 className="text-xl font-bold">Get set up in 3 steps</h1>
          <ul className="mt-2"><Step n={1} done={me.has_key} title="Add your Claude API key" body="You pay Anthropic directly. Your spending is capped." to="/settings" cta="Add key" />
            <Step n={2} done={me.has_profile} title="Upload your CV" body="PDF, Word or text. It becomes a draft profile." to="/profile" cta="Upload" />
            <Step n={3} done={me.profile_confirmed} title="Check and confirm your profile" body="Only facts you confirm are ever used." to="/profile" cta="Review" /></ul></Card>
      )}
      <Card delay={0.05}>
        <div className="flex flex-wrap items-center gap-4">
          <div className="min-w-0 flex-1"><h2 className="text-lg font-bold">Today's search</h2>
            <p className="mt-1 text-sm text-slate-500"><ShieldCheck className="mr-1 inline h-4 w-4 text-emerald-500" />Dry run: it only drafts. Nothing is sent anywhere.</p></div>
          <button className="btn" disabled={!ready || running || busy} onClick={run}>{running || busy ? <Spinner /> : <Play className="h-4 w-4" />}{running ? "Searching…" : "Find jobs now"}</button>
        </div>
        {me.run && (
          <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }} className="mt-4 rounded-xl bg-slate-100 p-3 text-sm dark:bg-white/5">
            <Pill tone={me.run.state === "done" ? "good" : me.run.state === "error" ? "bad" : "warn"}>{me.run.state === "running" ? "Running" : me.run.state === "done" ? "Finished" : "Failed"}</Pill>
            <span className="ml-2">{me.run.msg}</span>
            {running && <div className="mt-3 h-1.5 overflow-hidden rounded-full bg-slate-200 dark:bg-white/10"><motion.div className="h-full w-1/3 rounded-full bg-brand-500" animate={{ x: ["-100%", "300%"] }} transition={{ repeat: Infinity, duration: 1.6, ease: "easeInOut" }} /></div>}
          </motion.div>
        )}
      </Card>
      <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
        {stats.map(([label, n, s], i) => (
          <Link key={s} to={`/queue?status=${s}`}><motion.div initial={{ opacity: 0, y: 12 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.1 + i * 0.05 }} whileHover={{ y: -3 }} className="glass p-4 text-center">
            <p className="text-3xl font-bold">{n}</p><p className="text-sm text-slate-500">{label}</p></motion.div></Link>
        ))}
      </div>
      {me.has_key && (
        <Card delay={0.2}><div className="flex items-center justify-between"><h2 className="font-bold"><KeyRound className="mr-1 inline h-4 w-4" />API spend this month</h2><span className="text-sm text-slate-500">€{me.spent_eur.toFixed(2)} of €{me.cap_eur.toFixed(2)}</span></div>
          <div className="mt-3 h-2.5 overflow-hidden rounded-full bg-slate-200 dark:bg-white/10"><motion.div className={`h-full rounded-full ${pct > 80 ? "bg-amber-500" : "bg-brand-500"}`} initial={{ width: 0 }} animate={{ width: `${pct}%` }} transition={{ duration: 0.8 }} /></div></Card>
      )}
      {ready && <p className="text-center text-xs text-slate-500"><UserRound className="mr-1 inline h-3 w-3" />Profile confirmed · searches also run automatically every day</p>}
    </div>
  );
}
