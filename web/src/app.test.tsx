import { describe, expect, it, vi, beforeEach } from "vitest";
import { render, screen, waitFor, fireEvent } from "@testing-library/react";
import { HashRouter } from "react-router-dom";
import App from "./App";
import { AuthProvider } from "./lib/auth";
import { ToastProvider } from "./lib/toast";

const ME = { email: "ada@example.com", has_key: true, has_profile: true, profile_confirmed: true, draft_pending: false,
  counts: { drafted: 1, approved: 0, submitted: 0, rejected: 0 }, cap_eur: 15, spent_eur: 0.0025, run: null, min_salary_eur: 80000, min_score: 75 };
const ITEM = { id: "a1", title: "Senior Backend Engineer", company: "Acme", url: "https://x.test/1", status: "drafted", score: 88, reasons: ["Python"],
  red_flags: [], quota_remaining: 3, quota_max: 3, quota_allowed: true, quota_reason: "3 left", cv: "CV TEXT", letter: "LETTER TEXT" };

type Handler = (path: string, init?: RequestInit) => unknown;
function mockFetch(h: Handler) {
  globalThis.fetch = vi.fn(async (url: RequestInfo | URL, init?: RequestInit) => {
    const path = String(url).replace("http://api.test/api", "");
    const body = h(path, init);
    if (body instanceof Response) return body;
    return new Response(JSON.stringify(body), { status: 200, headers: { "Content-Type": "application/json" } });
  }) as typeof fetch;
}
function mount(route = "/") {
  window.location.hash = "#" + route;
  return render(<HashRouter><ToastProvider><AuthProvider><App /></AuthProvider></ToastProvider></HashRouter>);
}

beforeEach(() => { localStorage.clear(); localStorage.setItem("jobagent.api", "http://api.test"); });

describe("signed out", () => {
  it("redirects to login and shows the form", async () => {
    mockFetch(() => ({ required: false }));
    mount("/queue");
    expect(await screen.findByText("Welcome back")).toBeInTheDocument();
  });
  it("shows the server's error on a wrong password", async () => {
    mockFetch((p) => p === "/login" ? new Response(JSON.stringify({ detail: "Wrong email or password." }), { status: 400 }) : { required: false });
    mount("/login");
    fireEvent.change(await screen.findByLabelText("Email"), { target: { value: "a@b.ie" } });
    fireEvent.change(screen.getByLabelText("Password"), { target: { value: "wrongwrongwrong" } });
    fireEvent.click(screen.getByRole("button", { name: /log in/i }));
    expect(await screen.findByRole("alert")).toHaveTextContent("Wrong email or password.");
  });
  it("asks for the invite code only when the server requires it", async () => {
    mockFetch(() => ({ required: true }));
    mount("/signup");
    expect(await screen.findByLabelText("Invite code")).toBeInTheDocument();
  });
});

describe("signed in", () => {
  beforeEach(() => localStorage.setItem("jobagent.token", "tok"));

  it("dashboard shows counts, spend and enables the run button", async () => {
    mockFetch(() => ME);
    mount("/");
    expect(await screen.findByText("Today's search")).toBeInTheDocument();
    expect(screen.getByText("To review")).toBeInTheDocument();
    expect(screen.getByText(/€0.00 of €15.00/)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /find jobs now/i })).toBeEnabled();
  });
  it("dashboard blocks the run button and shows setup steps until the profile is confirmed", async () => {
    mockFetch(() => ({ ...ME, profile_confirmed: false, has_profile: false }));
    mount("/");
    expect(await screen.findByText("Get set up in 3 steps")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /find jobs now/i })).toBeDisabled();
  });
  it("queue lists drafts with score and quota", async () => {
    mockFetch((p) => p === "/me" ? ME : [ITEM]);
    mount("/queue");
    expect(await screen.findByText("Senior Backend Engineer")).toBeInTheDocument();
    expect(screen.getByText("3 of 3 applications left at Acme")).toBeInTheDocument();
    expect(screen.getByLabelText("Match score 88")).toBeInTheDocument();
  });
  it("application page approves and calls the right endpoint", async () => {
    const calls: string[] = [];
    mockFetch((p, init) => { calls.push((init?.method || "GET") + " " + p); return p === "/me" ? ME : p.endsWith("/approve") ? { status: "approved" } : ITEM; });
    mount("/application/a1");
    fireEvent.click(await screen.findByRole("button", { name: /approve/i }));
    await waitFor(() => expect(calls).toContain("POST /applications/a1/approve"));
    expect(calls.some((c) => c.includes("/applied"))).toBe(false);
  });
  it("approve is disabled when the company limit is reached", async () => {
    mockFetch((p) => p === "/me" ? ME : { ...ITEM, quota_allowed: false, quota_remaining: 0, quota_reason: "quota reached (3/3 in 180d)" });
    mount("/application/a1");
    expect(await screen.findByRole("button", { name: /approve/i })).toBeDisabled();
    expect(screen.getByText(/quota reached/)).toBeInTheDocument();
  });
  it("sends the bearer token and signs out on 401", async () => {
    const seen: (string | null)[] = [];
    mockFetch((p, init) => { seen.push(new Headers(init?.headers).get("Authorization")); return p === "/me" ? new Response("{}", { status: 401 }) : {}; });
    mount("/");
    expect(await screen.findByText("Welcome back")).toBeInTheDocument();
    expect(seen[0]).toBe("Bearer tok");
    expect(localStorage.getItem("jobagent.token")).toBeNull();
  });
  it("confirmed profile fields are read-only", async () => {
    const data = { name: "Ada", email: "", phone: "", location: "", headline: "", summary: "", skills: ["Python"], experience: [], education: [], certifications: [], languages: [], links: [], work_authorization: "", target_roles: [], years_experience: 6 };
    mockFetch((p) => p === "/me" ? ME : { exists: true, version: 1, confirmed: true, data });
    mount("/profile");
    const name = await screen.findByDisplayValue("Ada");
    expect(name).toBeDisabled();
    expect(screen.getByRole("button", { name: /edit \(new draft\)/i })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /confirm profile/i })).toBeNull();
  });
  it("delete button needs the word DELETE", async () => {
    mockFetch((p) => p === "/me" ? ME : p === "/key" ? { saved: true, masked: "****1234", cap_eur: 15 } : {});
    mount("/settings");
    const btn = await screen.findByRole("button", { name: /delete my account/i });
    expect(btn).toBeDisabled();
    fireEvent.change(screen.getByLabelText(/type delete/i), { target: { value: "DELETE" } });
    expect(btn).toBeEnabled();
    expect(await screen.findByText("****1234")).toBeInTheDocument();
  });
});
