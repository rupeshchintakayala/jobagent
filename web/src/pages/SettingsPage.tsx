import { useEffect, useState, type FormEvent } from "react";
import { useNavigate } from "react-router-dom";
import { KeyRound, ShieldAlert, SlidersHorizontal, Trash2 } from "lucide-react";
import { api } from "../lib/api";
import { useAuth } from "../lib/auth";
import { useToast } from "../lib/toast";
import { Card, Pill, Spinner } from "../components/ui";

export default function SettingsPage() {
  const { me, refresh, signOut } = useAuth();
  const toast = useToast();
  const nav = useNavigate();
  const [saved, setSaved] = useState<{ saved: boolean; masked?: string; cap_eur?: number } | null>(null);
  const [key, setKey] = useState(""); const [cap, setCap] = useState(15);
  const [salary, setSalary] = useState(me?.min_salary_eur ?? 80000); const [score, setScore] = useState(me?.min_score ?? 75);
  const [confirm, setConfirm] = useState(""); const [busy, setBusy] = useState("");

  useEffect(() => { api.getKey().then((k) => { setSaved(k); if (k.cap_eur) setCap(k.cap_eur); }).catch(() => {}); }, []);

  async function saveKey(e: FormEvent) {
    e.preventDefault(); setBusy("key");
    try { const r = await api.saveKey(key, cap); setKey(""); setSaved({ saved: true, masked: r.masked, cap_eur: r.cap_eur }); await refresh(); toast("ok", `Key saved (${r.masked}). Monthly cap €${r.cap_eur.toFixed(2)}.`); }
    catch (err) { toast("err", (err as Error).message); } finally { setBusy(""); }
  }
  async function savePrefs(e: FormEvent) {
    e.preventDefault(); setBusy("prefs");
    try { await api.savePrefs(salary, score); await refresh(); toast("ok", "Preferences saved."); } catch (err) { toast("err", (err as Error).message); } finally { setBusy(""); }
  }
  async function del() {
    setBusy("del");
    try { await api.deleteAccount(confirm); signOut(); nav("/login"); } catch (err) { toast("err", (err as Error).message); } finally { setBusy(""); }
  }

  return (
    <div className="space-y-4">
      <Card><h1 className="flex items-center gap-2 text-xl font-bold"><KeyRound className="h-5 w-5 text-brand-500" />Claude API key</h1>
        {saved?.saved && <p className="mt-2"><Pill tone="good">Saved</Pill> <code className="ml-1 text-sm">{saved.masked}</code> <span className="text-sm text-slate-500">· cap €{saved.cap_eur?.toFixed(2)}/month</span></p>}
        <p className="mt-2 text-sm text-slate-500">Get a key at console.anthropic.com. It's encrypted on the server and never shown again. You pay Anthropic directly; usage stops at your cap.</p>
        <form onSubmit={saveKey}><label className="label" htmlFor="k">{saved?.saved ? "Replace key" : "API key"}</label>
          <input id="k" className="input" type="password" autoComplete="off" placeholder="sk-ant-..." value={key} onChange={(e) => setKey(e.target.value)} required />
          <label className="label" htmlFor="c">Monthly cap (€)</label><input id="c" className="input" type="number" min={1} max={500} value={cap} onChange={(e) => setCap(Number(e.target.value))} />
          <button className="btn mt-4" disabled={busy === "key"}>{busy === "key" && <Spinner />}Verify and save</button></form></Card>
      <Card delay={0.05}><h2 className="flex items-center gap-2 text-lg font-bold"><SlidersHorizontal className="h-5 w-5 text-brand-500" />Search preferences</h2>
        <form onSubmit={savePrefs}><label className="label" htmlFor="s">Minimum salary (€/year)</label><input id="s" className="input" type="number" min={0} step={1000} value={salary} onChange={(e) => setSalary(Number(e.target.value))} />
          <label className="label" htmlFor="m">Minimum match score (0-100)</label><input id="m" className="input" type="number" min={0} max={100} value={score} onChange={(e) => setScore(Number(e.target.value))} />
          <p className="mt-2 text-xs text-slate-500">Jobs with no published salary are shown separately, not dropped.</p>
          <button className="btn mt-4" disabled={busy === "prefs"}>{busy === "prefs" && <Spinner />}Save</button></form></Card>
      <Card delay={0.1} className="border-rose-500/30"><h2 className="flex items-center gap-2 text-lg font-bold"><ShieldAlert className="h-5 w-5 text-rose-500" />Delete everything</h2>
        <p className="mt-1 text-sm text-slate-500">Permanently removes your account, key, profiles, drafts and history. This cannot be undone.</p>
        <label className="label" htmlFor="d">Type DELETE to confirm</label><input id="d" className="input" autoComplete="off" value={confirm} onChange={(e) => setConfirm(e.target.value)} />
        <button className="btn btn-bad mt-4" disabled={confirm.trim().toLowerCase() !== "delete" || busy === "del"} onClick={del}>{busy === "del" ? <Spinner /> : <Trash2 className="h-4 w-4" />}Delete my account and data</button></Card>
    </div>
  );
}
