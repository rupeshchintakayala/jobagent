import { useEffect, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { AlertTriangle, ArrowLeft, Check, CheckCircle2, ExternalLink, Send, ShieldAlert, X } from "lucide-react";
import { api, type AppItem } from "../lib/api";
import { useAuth } from "../lib/auth";
import { useToast } from "../lib/toast";
import { Card, PageLoader, Pill, QuotaBadge, ScoreRing, Spinner } from "../components/ui";

export default function ApplicationPage() {
  const { id = "" } = useParams();
  const nav = useNavigate();
  const toast = useToast();
  const { refresh } = useAuth();
  const [a, setA] = useState<AppItem | null>(null);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState("");

  const load = () => api.application(id).then(setA).catch((e: Error) => setError(e.message));
  useEffect(() => { void load(); /* eslint-disable-next-line */ }, [id]);

  async function act(action: "approve" | "reject" | "applied", msg: string) {
    setBusy(action);
    try { await api.act(id, action); toast("ok", msg); await refresh(); if (action === "approve") await load(); else nav("/queue"); }
    catch (e) { toast("err", (e as Error).message); } finally { setBusy(""); }
  }

  if (error) return <Card><p role="alert" className="text-rose-500">{error}</p><Link className="btn-ghost mt-4" to="/queue">Back</Link></Card>;
  if (!a) return <PageLoader />;
  return (
    <div className="space-y-4">
      <Link to="/queue" className="inline-flex items-center gap-1 text-sm text-slate-500 hover:text-brand-500"><ArrowLeft className="h-4 w-4" />Review queue</Link>
      <Card>
        <div className="flex items-start gap-4"><ScoreRing score={a.score} />
          <div className="min-w-0 flex-1"><h1 className="text-xl font-bold">{a.title}</h1><p className="text-slate-500">{a.company}{a.location ? ` · ${a.location}` : ""}</p>
            <div className="mt-2 flex flex-wrap items-center gap-2"><Pill tone="brand">{a.status}</Pill><QuotaBadge remaining={a.quota_remaining} max={a.quota_max} company={a.company} /></div></div></div>
        <a href={a.url} target="_blank" rel="noopener noreferrer" className="mt-4 inline-flex items-center gap-1 text-sm font-medium text-brand-500">Open the job posting<ExternalLink className="h-4 w-4" /></a>
        {!a.quota_allowed && <p className="mt-3 rounded-lg bg-rose-500/10 p-3 text-sm text-rose-600 dark:text-rose-300"><ShieldAlert className="mr-1 inline h-4 w-4" />{a.quota_reason}</p>}
        {a.reasons.length > 0 && <p className="mt-3 text-sm"><CheckCircle2 className="mr-1 inline h-4 w-4 text-emerald-500" />{a.reasons.join(" · ")}</p>}
        {a.red_flags.length > 0 && <p className="mt-1 text-sm text-amber-600 dark:text-amber-300"><AlertTriangle className="mr-1 inline h-4 w-4" />{a.red_flags.join(" · ")}</p>}
      </Card>
      <Card delay={0.05}><h2 className="font-bold">Tailored CV</h2><pre className="mt-2 whitespace-pre-wrap rounded-xl bg-slate-100 p-4 text-sm leading-relaxed dark:bg-black/30">{a.cv}</pre>
        <h2 className="mt-5 font-bold">Cover letter</h2><pre className="mt-2 whitespace-pre-wrap rounded-xl bg-slate-100 p-4 text-sm leading-relaxed dark:bg-black/30">{a.letter}</pre>
        <p className="mt-3 text-xs text-slate-500">Every claim was checked against your confirmed profile. Still read it before you apply.</p></Card>
      <Card delay={0.1}>
        <div className="flex flex-wrap gap-3">
          {a.status === "drafted" && <button className="btn btn-ok" disabled={!a.quota_allowed || !!busy} onClick={() => act("approve", "Approved. Apply on the company site, then click “I applied”.")}>{busy === "approve" ? <Spinner /> : <Check className="h-4 w-4" />}Approve</button>}
          {a.status === "approved" && <button className="btn" disabled={!!busy} onClick={() => act("applied", "Recorded as applied.")}>{busy === "applied" ? <Spinner /> : <Send className="h-4 w-4" />}I applied</button>}
          {(a.status === "drafted" || a.status === "approved") && <button className="btn btn-bad" disabled={!!busy} onClick={() => act("reject", "Rejected.")}>{busy === "reject" ? <Spinner /> : <X className="h-4 w-4" />}Reject</button>}
        </div>
        {a.status === "drafted" && <p className="mt-3 text-xs text-slate-500">Approving sends nothing. It reserves one of your applications at this company. You then apply yourself on their site and click “I applied”.</p>}
      </Card>
    </div>
  );
}
