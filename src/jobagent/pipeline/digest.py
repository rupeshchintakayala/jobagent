"""Markdown digest of the review queue."""
from __future__ import annotations
from .daily import DailyReport


def render_digest(rep: DailyReport, cap_eur: float | None = None) -> str:
    L = ["# Daily job digest", "",
         f"Fetched **{rep.fetched}** · filtered out **{rep.filtered_out}** · scored **{rep.scored}** · "
         f"queued **{len(rep.queue)}** · spent **€{rep.spent_eur:.4f}**" + (f" of €{cap_eur:.2f}" if cap_eur else ""), ""]
    if rep.budget_stopped:
        L += ["> ⚠️ Monthly API budget reached: some jobs were not scored. Raise your cap or wait for next month.", ""]
    known = [c for c in rep.queue if not c.salary_unknown]
    unknown = [c for c in rep.queue if c.salary_unknown]

    def section(title: str, items):
        nonlocal L
        if not items:
            return
        L.append(f"## {title}")
        for c in items:
            j = c.job
            quota = ""
            if c.quota_remaining is not None and c.quota_max:
                quota = f" · **{c.quota_remaining} of {c.quota_max} applications left** at {j.company}"
            L += [f"### {j.title} — {j.company} ({j.location}) · score **{c.score}**{quota}", f"{j.url}", ""]
            if c.reasons:
                L += ["Why it fits: " + "; ".join(c.reasons)]
            if c.red_flags:
                L += ["⚠️ Check: " + "; ".join(c.red_flags)]
            L += ["", "<details><summary>Tailored CV</summary>\n", c.cv, "\n</details>",
                  "<details><summary>Cover letter</summary>\n", c.letter, "\n</details>",
                  f"_Status: drafted (dry-run). Approve with `jobagent approve {c.application_id}`_", ""]

    section("Published salary meets your minimum", known)
    section("Salary not published (check before applying)", unknown)
    if rep.quota_blocked:
        L += ["## Skipped: company application limit reached"] + [f"- {j.title} at {j.company}: {r}" for j, r in rep.quota_blocked] + [""]
    if rep.tailoring_rejected:
        L += ["## Skipped: drafts failed the fact-check (nothing invented is ever shown)"] + \
             [f"- {j.title} at {j.company}: {'; '.join(v[:2])}" for j, v in rep.tailoring_rejected] + [""]
    if rep.below_threshold:
        L += ["## Below your score threshold"] + [f"- {j.title} at {j.company}: {s}" for j, s in rep.below_threshold[:15]] + [""]
    if rep.errors:
        L += ["## Errors"] + [f"- {e}" for e in rep.errors] + [""]
    return "\n".join(L)
