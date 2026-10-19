import { useEffect, useState, type FormEvent } from "react";
import { Scale } from "lucide-react";
import { api, type PolicyRow } from "../lib/api";
import { useToast } from "../lib/toast";
import { Card, Pill, Skeleton, Spinner } from "../components/ui";

export default function LimitsPage() {
  const toast = useToast();
  const [rows, setRows] = useState<PolicyRow[] | null>(null);
  const [company, setCompany] = useState(""); const [max, setMax] = useState(""); const [win, setWin] = useState(180); const [note, setNote] = useState("");
  const [busy, setBusy] = useState(false);
  const load = () => api.policies().then(setRows).catch((e: Error) => toast("err", e.message));
  useEffect(() => { void load(); /* eslint-disable-next-line */ }, []);

  async function submit(e: FormEvent) {
    e.preventDefault(); setBusy(true);
    try { await api.setPolicy(company.trim(), max.trim() === "" ? null : Number(max), win, note); toast("ok", `Saved limit for ${company}.`); setCompany(""); setMax(""); setNote(""); await load(); }
    catch (err) { toast("err", (err as Error).message); } finally { setBusy(false); }
  }
  return (
    <div className="space-y-4">
      <Card><h1 className="flex items-center gap-2 text-xl font-bold"><Scale className="h-5 w-5 text-brand-500" />Company application limits</h1>
        <p className="mt-2 text-sm text-slate-500">Some companies cap how often you can apply (for example 5, then a 6-month lockout). Unknown companies default to <b>3</b> to be safe. Only enter limits you have read on the company's careers page.</p>
        <form onSubmit={submit}><label className="label" htmlFor="co">Company</label><input id="co" className="input" value={company} onChange={(e) => setCompany(e.target.value)} required />
          <div className="grid gap-x-4 md:grid-cols-2"><div><label className="label" htmlFor="mx">Max applications (empty = no limit)</label><input id="mx" className="input" inputMode="numeric" value={max} onChange={(e) => setMax(e.target.value)} /></div>
            <div><label className="label" htmlFor="w">Window (days)</label><input id="w" className="input" type="number" min={1} value={win} onChange={(e) => setWin(Number(e.target.value))} /></div></div>
          <label className="label" htmlFor="n">Source (e.g. careers page URL)</label><input id="n" className="input" value={note} onChange={(e) => setNote(e.target.value)} />
          <button className="btn mt-4" disabled={busy}>{busy && <Spinner />}Save limit</button></form></Card>
      <Card delay={0.05}><h2 className="font-bold">Known companies</h2>
        {!rows ? <Skeleton className="mt-3 h-24" /> : rows.length === 0 ? <p className="mt-2 text-sm text-slate-500">No companies yet. They appear after the first search.</p> :
          <ul className="mt-2 divide-y divide-slate-200 dark:divide-white/10">{rows.map((r) => (
            <li key={r.id} className="flex items-center gap-3 py-2.5"><span className="flex-1 font-medium">{r.name}</span>
              {r.window_days === null ? <Pill>unknown · default 3</Pill> : r.max_applications === null ? <Pill tone="good">no limit</Pill> : <Pill tone="warn">{r.max_applications} per {r.window_days}d</Pill>}</li>))}</ul>}</Card>
    </div>
  );
}
