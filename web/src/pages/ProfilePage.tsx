import { useEffect, useState, type ChangeEvent } from "react";
import { Link } from "react-router-dom";
import { FileUp, Lock, Plus, Save, ShieldCheck, Trash2 } from "lucide-react";
import { api, type Profile, type ProfileResp } from "../lib/api";
import { useAuth } from "../lib/auth";
import { useToast } from "../lib/toast";
import { Card, PageLoader, Pill, Spinner } from "../components/ui";

const lines = (v: string) => v.split("\n").map((x) => x.trim()).filter(Boolean);

function List({ label, hint, value, onChange, disabled }: { label: string; hint?: string; value: string[]; onChange: (v: string[]) => void; disabled: boolean }) {
  const [text, setText] = useState(value.join("\n"));
  return (<><label className="label">{label} {hint && <span className="font-normal text-slate-500">({hint})</span>}</label>
    <textarea className="input min-h-[80px]" disabled={disabled} value={text} onChange={(e) => { setText(e.target.value); onChange(lines(e.target.value)); }} /></>);
}
function Field({ label, value, onChange, disabled }: { label: string; value: string; onChange: (v: string) => void; disabled: boolean }) {
  return (<div><label className="label">{label}</label><input className="input" disabled={disabled} value={value} onChange={(e) => onChange(e.target.value)} /></div>);
}

export default function ProfilePage() {
  const { me, refresh } = useAuth();
  const toast = useToast();
  const [resp, setResp] = useState<ProfileResp | null>(null);
  const [p, setP] = useState<Profile | null>(null);
  const [busy, setBusy] = useState("");

  const load = async () => { const r = await api.profile(); setResp(r); setP(r.exists ? r.data : null); };
  useEffect(() => { void load(); }, []);
  if (!resp || !me) return <PageLoader />;

  async function onFile(e: ChangeEvent<HTMLInputElement>) {
    const f = e.target.files?.[0]; if (!f) return;
    setBusy("upload");
    try { await api.upload(f); toast("ok", "Draft created. Check every fact, fix anything wrong, then confirm."); await load(); await refresh(); }
    catch (err) { toast("err", (err as Error).message); } finally { setBusy(""); e.target.value = ""; }
  }
  async function save(confirm: boolean) {
    if (!p) return; setBusy(confirm ? "confirm" : "save");
    try { await api.saveProfile(p, confirm); toast("ok", confirm ? "Profile confirmed. Only these facts will be used." : "Draft saved."); await load(); await refresh(); }
    catch (err) { toast("err", (err as Error).message); } finally { setBusy(""); }
  }
  async function newVersion() {
    setBusy("new"); try { await api.newVersion(); await load(); await refresh(); toast("ok", "New draft created from your confirmed profile."); }
    catch (err) { toast("err", (err as Error).message); } finally { setBusy(""); }
  }

  const upload = (label: string) => (
    <label className={`btn cursor-pointer ${busy === "upload" ? "pointer-events-none opacity-60" : ""}`}>{busy === "upload" ? <Spinner /> : <FileUp className="h-4 w-4" />}{label}
      <input type="file" className="hidden" accept=".pdf,.docx,.txt,.md" onChange={onFile} /></label>);

  if (!resp.exists || !p) {
    return (<Card><h1 className="text-xl font-bold">Upload your CV</h1>
      {!me.has_key ? <p className="mt-2 text-sm">Add your <Link className="text-brand-500" to="/settings">Claude key</Link> first.</p>
        : <><p className="mb-4 mt-1 text-sm text-slate-500">PDF, Word (.docx) or text, up to 5 MB. Reading it takes about 20 seconds.</p>{upload("Choose your CV")}</>}</Card>);
  }
  const locked = resp.confirmed;
  const set = <K extends keyof Profile>(k: K, v: Profile[K]) => setP({ ...p, [k]: v });

  return (
    <div className="space-y-4">
      <Card><div className="flex flex-wrap items-center gap-3"><h1 className="flex-1 text-xl font-bold">Your profile</h1>
        <Pill tone={locked ? "good" : "warn"}>v{resp.version} · {locked ? "confirmed" : "draft: needs your check"}</Pill></div>
        {locked ? <div className="mt-3 flex flex-wrap items-center gap-3"><p className="flex-1 text-sm text-slate-500"><Lock className="mr-1 inline h-4 w-4" />Confirmed and in use. To change anything, make a new draft.</p>
          <button className="btn-ghost" onClick={newVersion} disabled={busy === "new"}>Edit (new draft)</button></div>
          : <p className="mt-2 text-sm"><ShieldCheck className="mr-1 inline h-4 w-4 text-amber-500" /><b>Check every line.</b> The AI may have misread your CV. What you confirm here is the only source of truth for your applications.</p>}</Card>
      <Card delay={0.04}><h2 className="font-bold">About you</h2>
        <div className="grid gap-x-4 md:grid-cols-2">
          <Field label="Name" value={p.name} onChange={(v) => set("name", v)} disabled={locked} /><Field label="Email" value={p.email} onChange={(v) => set("email", v)} disabled={locked} />
          <Field label="Phone" value={p.phone} onChange={(v) => set("phone", v)} disabled={locked} /><Field label="Location" value={p.location} onChange={(v) => set("location", v)} disabled={locked} />
          <Field label="Headline" value={p.headline} onChange={(v) => set("headline", v)} disabled={locked} />
          <Field label="Work authorization (e.g. Irish citizen, Stamp 1G)" value={p.work_authorization} onChange={(v) => set("work_authorization", v)} disabled={locked} />
          <div><label className="label">Years of experience</label><input className="input" disabled={locked} inputMode="decimal" value={p.years_experience ?? ""} onChange={(e) => set("years_experience", e.target.value === "" ? null : Number(e.target.value) || 0)} /></div></div>
        <label className="label">Summary</label><textarea className="input min-h-[90px]" disabled={locked} value={p.summary} onChange={(e) => set("summary", e.target.value)} />
        <List label="Skills" hint="one per line" value={p.skills} onChange={(v) => set("skills", v)} disabled={locked} />
        <List label="Target roles" hint="one per line" value={p.target_roles} onChange={(v) => set("target_roles", v)} disabled={locked} /></Card>
      {p.experience.map((e, i) => {
        const up = (patch: Partial<typeof e>) => set("experience", p.experience.map((x, j) => (j === i ? { ...x, ...patch } : x)));
        return (<Card key={i} delay={0.06}><div className="flex items-center"><h2 className="flex-1 font-bold">Experience {i + 1}</h2>
          {!locked && <button aria-label="Remove experience" className="btn-ghost !p-2" onClick={() => set("experience", p.experience.filter((_, j) => j !== i))}><Trash2 className="h-4 w-4" /></button>}</div>
          <div className="grid gap-x-4 md:grid-cols-2"><Field label="Company" value={e.company} onChange={(v) => up({ company: v })} disabled={locked} /><Field label="Title" value={e.title} onChange={(v) => up({ title: v })} disabled={locked} />
            <Field label="Start" value={e.start} onChange={(v) => up({ start: v })} disabled={locked} /><Field label="End" value={e.end} onChange={(v) => up({ end: v })} disabled={locked} /></div>
          <label className="label">Summary</label><textarea className="input" disabled={locked} value={e.summary} onChange={(ev) => up({ summary: ev.target.value })} />
          <List label="Achievements" hint="one per line; keep numbers exact" value={e.achievements} onChange={(v) => up({ achievements: v })} disabled={locked} />
          <List label="Technologies" hint="one per line" value={e.technologies} onChange={(v) => up({ technologies: v })} disabled={locked} /></Card>);
      })}
      {p.education.map((ed, i) => {
        const up = (patch: Partial<typeof ed>) => set("education", p.education.map((x, j) => (j === i ? { ...x, ...patch } : x)));
        return (<Card key={i} delay={0.06}><h2 className="font-bold">Education {i + 1}</h2><div className="grid gap-x-4 md:grid-cols-2">
          <Field label="Institution" value={ed.institution} onChange={(v) => up({ institution: v })} disabled={locked} /><Field label="Degree" value={ed.degree} onChange={(v) => up({ degree: v })} disabled={locked} />
          <Field label="Field" value={ed.field} onChange={(v) => up({ field: v })} disabled={locked} /><Field label="Year" value={ed.year} onChange={(v) => up({ year: v })} disabled={locked} /></div></Card>);
      })}
      <Card delay={0.08}><h2 className="font-bold">Other</h2>
        <List label="Certifications" hint="one per line" value={p.certifications} onChange={(v) => set("certifications", v)} disabled={locked} />
        <List label="Languages" hint="one per line" value={p.languages} onChange={(v) => set("languages", v)} disabled={locked} />
        <List label="Links" hint="one per line" value={p.links} onChange={(v) => set("links", v)} disabled={locked} />
        {!locked && <button className="btn-ghost mt-4" onClick={() => set("experience", [...p.experience, { company: "", title: "", start: "", end: "", summary: "", achievements: [], technologies: [] }])}><Plus className="h-4 w-4" />Add experience</button>}</Card>
      {!locked && <Card className="sticky bottom-20 md:bottom-4"><div className="flex flex-wrap gap-3">
        <button className="btn-ghost" disabled={!!busy} onClick={() => save(false)}>{busy === "save" ? <Spinner /> : <Save className="h-4 w-4" />}Save draft</button>
        <button className="btn btn-ok" disabled={!!busy} onClick={() => save(true)}>{busy === "confirm" ? <Spinner /> : <ShieldCheck className="h-4 w-4" />}I've checked it: confirm profile</button></div></Card>}
      {locked && <Card><h2 className="font-bold">Replace with a new CV</h2><p className="mb-3 mt-1 text-sm text-slate-500">Creates a new draft. Your confirmed profile stays in use until you confirm the new one.</p>{upload("Upload new CV")}</Card>}
    </div>
  );
}
