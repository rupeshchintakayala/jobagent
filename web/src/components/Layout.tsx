import { useEffect, useState, type ReactNode } from "react";
import { NavLink, useNavigate } from "react-router-dom";
import { motion } from "framer-motion";
import { Briefcase, Inbox, LogOut, Moon, Scale, Settings, Sparkles, Sun, UserRound } from "lucide-react";
import { useAuth } from "../lib/auth";

const links = [
  { to: "/", label: "Home", icon: Sparkles, end: true },
  { to: "/queue", label: "Review", icon: Inbox },
  { to: "/profile", label: "Profile", icon: UserRound },
  { to: "/limits", label: "Limits", icon: Scale },
  { to: "/settings", label: "Settings", icon: Settings },
];

export function useTheme() {
  const [dark, setDark] = useState(() => (localStorage.getItem("jobagent.theme") ?? "dark") === "dark");
  useEffect(() => {
    document.documentElement.classList.toggle("dark", dark);
    document.documentElement.classList.toggle("light", !dark);
    localStorage.setItem("jobagent.theme", dark ? "dark" : "light");
  }, [dark]);
  return [dark, () => setDark((d) => !d)] as const;
}

export function Backdrop() {
  return (
    <div aria-hidden className="pointer-events-none fixed inset-0 -z-10 overflow-hidden">
      <div className="absolute -left-32 -top-32 h-96 w-96 animate-float rounded-full bg-brand-500/20 blur-3xl" />
      <div className="absolute -right-24 top-1/3 h-80 w-80 animate-float rounded-full bg-fuchsia-500/10 blur-3xl [animation-delay:2s]" />
    </div>
  );
}

export function Layout({ children }: { children: ReactNode }) {
  const { me, signOut } = useAuth();
  const nav = useNavigate();
  const [dark, toggle] = useTheme();
  return (
    <div className="min-h-screen">
      <Backdrop />
      <header className="sticky top-0 z-40 border-b border-slate-200/70 bg-white/70 backdrop-blur-xl dark:border-white/10 dark:bg-[#0b0d17]/70">
        <div className="mx-auto flex max-w-5xl items-center gap-3 px-4 py-3">
          <div className="flex items-center gap-2 font-bold"><span className="grid h-8 w-8 place-items-center rounded-lg bg-gradient-to-br from-brand-500 to-fuchsia-500 text-white"><Briefcase className="h-4 w-4" /></span><span className="hidden sm:inline">Job agent</span></div>
          <nav className="ml-2 hidden gap-1 md:flex">
            {links.map((l) => (
              <NavLink key={l.to} to={l.to} end={l.end} className={({ isActive }) => `relative rounded-lg px-3 py-1.5 text-sm font-medium transition ${isActive ? "text-brand-600 dark:text-brand-400" : "text-slate-600 hover:text-slate-900 dark:text-slate-400 dark:hover:text-white"}`}>
                {({ isActive }) => (<>{isActive && <motion.span layoutId="nav-pill" className="absolute inset-0 -z-10 rounded-lg bg-brand-500/10" />}{l.label}</>)}
              </NavLink>
            ))}
          </nav>
          <div className="flex-1" />
          <span className="hidden text-xs text-slate-500 lg:inline">{me?.email}</span>
          <button aria-label="Toggle theme" onClick={toggle} className="btn-ghost !p-2">{dark ? <Sun className="h-4 w-4" /> : <Moon className="h-4 w-4" />}</button>
          <button aria-label="Log out" onClick={() => { signOut(); nav("/login"); }} className="btn-ghost !p-2"><LogOut className="h-4 w-4" /></button>
        </div>
      </header>
      <main className="mx-auto max-w-5xl px-4 pb-28 pt-6 md:pb-10">{children}</main>
      <nav className="fixed inset-x-0 bottom-0 z-40 flex justify-around border-t border-slate-200 bg-white/90 py-1.5 backdrop-blur-xl md:hidden dark:border-white/10 dark:bg-[#0b0d17]/90">
        {links.map((l) => (
          <NavLink key={l.to} to={l.to} end={l.end} className={({ isActive }) => `flex flex-col items-center gap-0.5 px-3 py-1 text-[11px] font-medium ${isActive ? "text-brand-600 dark:text-brand-400" : "text-slate-500"}`}>
            <l.icon className="h-5 w-5" />{l.label}
          </NavLink>
        ))}
      </nav>
    </div>
  );
}
