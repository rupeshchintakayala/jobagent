// All backend calls live here. The backend URL is chosen at build time (VITE_API_URL) or at runtime in the Connect screen.
const TOKEN_KEY = "jobagent.token";
const API_KEY = "jobagent.api";

export class ApiError extends Error {
  constructor(public status: number, message: string) { super(message); }
}

export const getToken = () => localStorage.getItem(TOKEN_KEY);
export const setToken = (t: string | null) => (t ? localStorage.setItem(TOKEN_KEY, t) : localStorage.removeItem(TOKEN_KEY));

export function apiBase(): string {
  const saved = localStorage.getItem(API_KEY) || (import.meta.env.VITE_API_URL as string | undefined) || "";
  return saved.replace(/\/+$/, "");
}
export function setApiBase(url: string) {
  const clean = url.trim().replace(/\/+$/, "");
  if (clean) localStorage.setItem(API_KEY, clean); else localStorage.removeItem(API_KEY);
}

type Opts = { method?: string; body?: unknown; form?: FormData };

export async function request<T>(path: string, opts: Opts = {}): Promise<T> {
  const base = apiBase();
  if (!base) throw new ApiError(0, "No backend address set.");
  const headers: Record<string, string> = {};
  const t = getToken();
  if (t) headers["Authorization"] = `Bearer ${t}`;
  let body: BodyInit | undefined;
  if (opts.form) body = opts.form;
  else if (opts.body !== undefined) { headers["Content-Type"] = "application/json"; body = JSON.stringify(opts.body); }
  let res: Response;
  try {
    res = await fetch(base + "/api" + path, { method: opts.method || "GET", headers, body });
  } catch {
    throw new ApiError(0, "Can't reach the backend. Is it running, and is the address right?");
  }
  if (res.status === 401 && t) { setToken(null); window.dispatchEvent(new Event("jobagent:signed-out")); }
  if (!res.ok) {
    let msg = res.statusText;
    try { const j = await res.json(); msg = typeof j.detail === "string" ? j.detail : "That didn't look right. Check the fields and try again."; } catch { /* keep statusText */ }
    throw new ApiError(res.status, msg);
  }
  return (await res.json()) as T;
}

export const api = {
  invite: () => request<{ required: boolean }>("/invite-required"),
  signup: (email: string, password: string, invite: string) => request<{ token: string; email: string }>("/signup", { method: "POST", body: { email, password, invite } }),
  login: (email: string, password: string) => request<{ token: string; email: string }>("/login", { method: "POST", body: { email, password } }),
  me: () => request<Me>("/me"),
  getKey: () => request<{ saved: boolean; masked?: string; cap_eur?: number }>("/key"),
  saveKey: (api_key: string, cap_eur: number) => request<{ masked: string; cap_eur: number }>("/key", { method: "PUT", body: { api_key, cap_eur } }),
  savePrefs: (min_salary_eur: number, min_score: number) => request<{ ok: boolean }>("/prefs", { method: "PUT", body: { min_salary_eur, min_score } }),
  profile: () => request<ProfileResp>("/profile"),
  upload: (file: File) => { const f = new FormData(); f.append("cv", file); return request<{ version: number }>("/profile/upload", { method: "POST", form: f }); },
  saveProfile: (p: Profile, confirm: boolean) => request<{ version: number; confirmed: boolean }>(`/profile?confirm=${confirm}`, { method: "PUT", body: p }),
  newVersion: () => request<{ version: number }>("/profile/new-version", { method: "POST" }),
  run: () => request<RunState>("/run", { method: "POST" }),
  applications: (status: Status) => request<AppItem[]>(`/applications?status=${status}`),
  application: (id: string) => request<AppItem>(`/applications/${id}`),
  act: (id: string, action: "approve" | "reject" | "applied") => request<{ status: string }>(`/applications/${id}/${action}`, { method: "POST" }),
  policies: () => request<PolicyRow[]>("/policies"),
  setPolicy: (company: string, max_applications: number | null, window_days: number, note: string) =>
    request<{ ok: boolean }>("/policies", { method: "PUT", body: { company, max_applications, window_days, note } }),
  deleteAccount: (confirm: string) => request<{ ok: boolean }>("/delete-account", { method: "POST", body: { confirm } }),
};

export type Status = "drafted" | "approved" | "submitted" | "rejected";
export type RunState = { state: "running" | "done" | "error"; msg: string } | null;
export interface Me {
  email: string; has_key: boolean; has_profile: boolean; profile_confirmed: boolean; draft_pending: boolean;
  counts: Record<Status, number>; cap_eur: number; spent_eur: number; run: RunState; min_salary_eur: number; min_score: number;
}
export interface Experience { company: string; title: string; start: string; end: string; summary: string; achievements: string[]; technologies: string[] }
export interface Education { institution: string; degree: string; field: string; year: string }
export interface Profile {
  name: string; email: string; phone: string; location: string; headline: string; summary: string; skills: string[];
  experience: Experience[]; education: Education[]; certifications: string[]; languages: string[]; links: string[];
  work_authorization: string; target_roles: string[]; years_experience: number | null;
}
export type ProfileResp = { exists: false } | { exists: true; version: number; confirmed: boolean; data: Profile };
export interface AppItem {
  id: string; title: string; company: string; url: string; status: Status; score: number | null; reasons: string[]; red_flags: string[];
  quota_remaining: number | null; quota_max: number; quota_allowed: boolean; quota_reason: string; cv?: string; letter?: string; location?: string;
}
export interface PolicyRow { id: string; name: string; max_applications: number | null; window_days: number | null; source_note: string | null }
