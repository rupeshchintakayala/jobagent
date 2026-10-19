import { useEffect, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { AnimatePresence, motion } from "framer-motion";
import { AlertTriangle, ArrowRight, CheckCircle2 } from "lucide-react";
import { api, type AppItem, type Status } from "../lib/api";
import { Empty, QuotaBadge, ScoreRing, Skeleton } from "../components/ui";

const TABS: [Status, string][] = [["drafted", "To review"], ["approved", "Approved"], ["submitted", "Applied"], ["rejected", "Rejected"]];

export default function Queue() {
  const [params, setParams] = useSearchParams();
  const status = (TABS.find(([s]) => s === params.get("status"))?.[0] ?? "drafted") as Status;
  const [items, setItems] = useState<AppItem[] | null>(null);
  const [error, setError] = useState("");

  useEffect(() => {
    setItems(null); setError("");
    api.applications(status).then(setItems).catch((e: Error) => setError(e.message));
  }, [status]);

  return (
    <div>
      <div className="mb-4 flex flex-wrap gap-2" role="tablist">
        {TABS.map(([s, label]) => (
          <button key={s} role="tab" aria-selected={s === status} onClick={() => setParams({ status: s })}
            className={`rounded-full px-4 py-1.5 text-sm font-semibold transition ${s === status ? "bg-brand-600 text-white" : "bg-slate-200/70 hover:bg-slate-200 dark:bg-white/5 dark:hover:bg-white/10"}`}>{label}</button>
        ))}
      </div>
      {error && <p role="alert" className="text-rose-500">{error}</p>}
      {!items && !error && <div className="space-y-3"><Skeleton /><Skeleton /><Skeleton /></div>}
      {items && items.length === 0 && <Empty title="Nothing here yet" body={status === "drafted" ? "Run a search from the Home page and your drafts appear here." : "Applications you move here will show up in this list."} action={status === "drafted" ? <Link className="btn" to="/">Go to Home</Link> : undefined} />}
      <AnimatePresence>
        {items?.map((a, i) => (
          <motion.div key={a.id} layout initial={{ opacity: 0, y: 16 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0 }} transition={{ delay: i * 0.04 }} className="mb-3">
            <Link to={`/application/${a.id}`} className="glass group flex items-center gap-4 p-4 transition hover:border-brand-500/50">
              <ScoreRing score={a.score} />
              <div className="min-w-0 flex-1">
                <h3 className="truncate font-semibold">{a.title}</h3>
                <p className="text-sm text-slate-500">{a.company}</p>
                <div className="mt-2 flex flex-wrap gap-2 text-xs"><QuotaBadge remaining={a.quota_remaining} max={a.quota_max} company={a.company} /></div>
                {a.reasons.length > 0 && <p className="mt-2 line-clamp-1 text-sm text-slate-600 dark:text-slate-300"><CheckCircle2 className="mr-1 inline h-4 w-4 text-emerald-500" />{a.reasons.join(" · ")}</p>}
                {a.red_flags.length > 0 && <p className="mt-1 line-clamp-1 text-sm text-amber-600 dark:text-amber-300"><AlertTriangle className="mr-1 inline h-4 w-4" />{a.red_flags.join(" · ")}</p>}
              </div>
              <ArrowRight className="h-5 w-5 text-slate-400 transition group-hover:translate-x-1" />
            </Link>
          </motion.div>
        ))}
      </AnimatePresence>
    </div>
  );
}
