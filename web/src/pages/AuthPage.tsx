import { useEffect, useState, type FormEvent } from "react";
import { Link, useNavigate } from "react-router-dom";
import { motion } from "framer-motion";
import { Briefcase, ShieldCheck, Sparkles, UserCheck } from "lucide-react";
import { api, apiBase, setApiBase } from "../lib/api";
import { useAuth } from "../lib/auth";
import { Backdrop } from "../components/Layout";
import { Spinner } from "../components/ui";

export default function AuthPage({ mode }: { mode: "login" | "signup" }) {
  const { signIn } = useAuth();
  const nav = useNavigate();
  const [server, setServer] = useState(apiBase());
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [invite, setInvite] = useState("");
  const [needInvite, setNeedInvite] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const signup = mode === "signup";

  useEffect(() => { if (server) api.invite().then((r) => setNeedInvite(r.required)).catch(() => setNeedInvite(false)); }, [server]);

  async function submit(e: FormEvent) {
    e.preventDefault(); setError(""); setBusy(true);
    try {
      setApiBase(server);
      const r = signup ? await api.signup(email, password, invite) : await api.login(email, password);
      await signIn(r.token);
      nav("/");
    } catch (err) { setError((err as Error).message); } finally { setBusy(false); }
  }

  return (
    <div className="grid min-h-screen place-items-center px-4 py-10">
      <Backdrop />
      <div className="grid w-full max-w-4xl items-center gap-10 md:grid-cols-2">
        <motion.div initial={{ opacity: 0, x: -20 }} animate={{ opacity: 1, x: 0 }} className="hidden md:block">
          <span className="grid h-12 w-12 place-items-center rounded-2xl bg-gradient-to-br from-brand-500 to-fuchsia-500 text-white"><Briefcase /></span>
          <h1 className="mt-6 text-4xl font-bold leading-tight">Find Dublin jobs.<br /><span className="bg-gradient-to-r from-brand-400 to-fuchsia-400 bg-clip-text text-transparent">Apply with facts only.</span></h1>
          <ul className="mt-6 space-y-3 text-sm text-slate-600 dark:text-slate-300">
            <li className="flex gap-2"><UserCheck className="h-5 w-5 shrink-0 text-emerald-500" />You approve every application. Nothing is sent for you.</li>
            <li className="flex gap-2"><ShieldCheck className="h-5 w-5 shrink-0 text-emerald-500" />Every claim is checked against facts you confirmed.</li>
            <li className="flex gap-2"><Sparkles className="h-5 w-5 shrink-0 text-emerald-500" />Your own Claude key, your own spending cap.</li>
          </ul>
        </motion.div>
        <motion.form onSubmit={submit} initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }} className="glass p-6">
          <h2 className="text-xl font-bold">{signup ? "Create your account" : "Welcome back"}</h2>
          {!apiBase() || !server ? <p className="mt-2 text-sm text-amber-600 dark:text-amber-300">Enter the server address you were given first.</p> : null}
          <label className="label" htmlFor="server">Server address</label>
          <input id="server" className="input" placeholder="https://something.trycloudflare.com" value={server} onChange={(e) => setServer(e.target.value)} required />
          <label className="label" htmlFor="email">Email</label>
          <input id="email" className="input" type="email" autoComplete="email" value={email} onChange={(e) => setEmail(e.target.value)} required />
          <label className="label" htmlFor="pw">Password {signup && <span className="font-normal text-slate-500">(10+ characters)</span>}</label>
          <input id="pw" className="input" type="password" autoComplete={signup ? "new-password" : "current-password"} minLength={signup ? 10 : undefined} value={password} onChange={(e) => setPassword(e.target.value)} required />
          {signup && needInvite && (<><label className="label" htmlFor="invite">Invite code</label><input id="invite" className="input" value={invite} onChange={(e) => setInvite(e.target.value)} required autoComplete="off" /></>)}
          {error && <p role="alert" className="mt-3 rounded-lg bg-rose-500/10 px-3 py-2 text-sm text-rose-600 dark:text-rose-300">{error}</p>}
          <button className="btn mt-5 w-full" disabled={busy}>{busy && <Spinner />}{signup ? "Sign up" : "Log in"}</button>
          <p className="mt-4 text-center text-sm text-slate-500">{signup ? <>Already registered? <Link className="font-medium text-brand-500" to="/login">Log in</Link></> : <>New here? <Link className="font-medium text-brand-500" to="/signup">Create an account</Link></>}</p>
        </motion.form>
      </div>
    </div>
  );
}
