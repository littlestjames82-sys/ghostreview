"""Core review builder: diff (+ optional Verify / Scope) -> report dict.

Static evidence only. Every number in the report is counted from the
diff or read from a supplied report; every sentence REVIEW.md prints
is templated from those numbers in reports.py. No causes are inferred:
if the inputs do not say why a change was made, the review does not say.
"""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from . import __version__
from .dependents import find_dependents
from .diffparse import parse_diff
from .inputs import load_scope_pack, load_verify_report
from .risks import flag_risks, verdict_for
from .symbols import symbols_for_change

HONESTY = ("this review summarises static evidence from the diff only; "
           "'no risks flagged by these rules' is not a guarantee that "
           "a change is safe, and the verdict is a summary, not a "
           "merge decision")


def build_review(project, diff_text: str, diff_source: str,
                 verify_report: str | None = None,
                 scope_pack: str | None = None,
                 extra_notes: list | None = None) -> dict:
    project_path = Path(project)
    notes = list(extra_notes or [])
    verify = load_verify_report(verify_report)
    scope = load_scope_pack(scope_pack)
    for label, rec in (("Verify", verify), ("Scope", scope)):
        if rec.get("unreadable"):
            notes.append(rec["unreadable"])

    changes = parse_diff(diff_text) if diff_text else []
    base = {
        "tool": "ghostreview", "version": __version__, "kind": "review",
        "project": str(project_path), "diff_source": diff_source,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "verify": verify, "scope": scope, "honesty": HONESTY,
    }
    if not changes:
        return {**base, "verdict": "could-not-review", "exit_code": 2,
                "verdict_summary": "No file changes were found in the "
                "supplied diff, so there is nothing to review. This is "
                "not a clean verdict.",
                "totals": {"files_changed": 0, "additions": 0,
                           "deletions": 0},
                "changes": [], "dependents": {}, "risks": [],
                "notes": notes + ["the diff was empty or could not be "
                                   "parsed into file changes"]}

    symbols_by_path = {}
    change_rows = []
    for c in changes:
        syms = symbols_for_change(project_path, c)
        symbols_by_path[c.path] = syms
        change_rows.append({
            "path": c.path, "old_path": c.old_path, "status": c.status,
            "additions": c.added_count, "deletions": c.deleted_count,
            "hunks": len(c.hunks), "is_binary": c.is_binary,
            "old_mode": c.old_mode, "new_mode": c.new_mode,
            "mode_changed": c.mode_changed,
            "symbols": syms,
        })
    diff_paths = {c.path for c in changes}
    dependents = find_dependents(project_path, diff_paths, diff_paths)
    risks = flag_risks(changes, symbols_by_path, dependents,
                       verify if verify.get("present") else None)
    verdict = verdict_for(risks)

    totals = {
        "files_changed": len(changes),
        "added_files": sum(1 for c in changes if c.status == "added"),
        "modified_files": sum(1 for c in changes if c.status == "modified"),
        "deleted_files": sum(1 for c in changes if c.status == "deleted"),
        "renamed_files": sum(1 for c in changes if c.status == "renamed"),
        "copied_files": sum(1 for c in changes if c.status == "copied"),
        "additions": sum(c.added_count for c in changes),
        "deletions": sum(c.deleted_count for c in changes),
        "symbols_touched": sum(len(s["symbols"]["touched"])
                               for s in change_rows),
        "dependent_files": len({d for e in dependents.values()
                                for d in e["dependents"]}),
        "risks_high": sum(1 for r in risks if r["level"] == "high"),
        "risks_medium": sum(1 for r in risks if r["level"] == "medium"),
        "risks_info": sum(1 for r in risks if r["level"] == "info"),
    }
    return {**base, "verdict": verdict,
            "exit_code": 1 if verdict == "needs-attention" else 0,
            "verdict_summary": _summary(totals, change_rows, dependents,
                                        risks, verdict, verify, scope),
            "totals": totals, "changes": change_rows,
            "dependents": dependents, "risks": risks, "notes": notes}


def _summary(totals, change_rows, dependents, risks, verdict,
             verify, scope) -> str:
    parts = []
    status_bits = []
    for key, label in (("added_files", "added"), ("modified_files", "modified"),
                       ("deleted_files", "deleted"), ("renamed_files", "renamed"),
                       ("copied_files", "copied")):
        if totals[key]:
            status_bits.append(f"{totals[key]} {label}")
    parts.append(
        f"This change touches {totals['files_changed']} file(s)"
        + (f" ({', '.join(status_bits)})" if status_bits else "")
        + f", with {totals['additions']} line(s) added and "
          f"{totals['deletions']} line(s) deleted.")
    if change_rows:
        biggest = max(change_rows,
                      key=lambda r: r["additions"] + r["deletions"])
        parts.append(
            f"The largest change is in {biggest['path']} "
            f"({biggest['additions']} added, {biggest['deletions']} deleted).")
    if totals["dependent_files"]:
        parts.append(
            f"{totals['dependent_files']} other project file(s) import a "
            "changed file and are not in this diff.")
    else:
        parts.append("No project file outside this diff was found to "
                     "import a changed file by the one-hop import scan.")
    if totals["risks_high"] or totals["risks_medium"]:
        # Cap the summary at the first few flags: the full list is
        # in the Risks section / review.json. An uncapped join made
        # the one-paragraph summary (and the MCP payload) grow with
        # every flag on a large diff.
        flagged = [r for r in risks if r["level"] in ("high", "medium")]
        top = "; ".join(f"{r['rule']} in {r['file']}: {r['detail']}"
                        for r in flagged[:3])
        more = len(flagged) - 3
        parts.append(f"Risks flagged: {top}"
                     + (f"; and {more} more risk(s), listed in the "
                        "Risks section below" if more > 0 else "") + ".")
    else:
        parts.append("No risks were flagged by the GhostReview rules.")
    if verify.get("present"):
        parts.append(f"GhostVerify verdict for this change: "
                     f"{verify.get('verdict')} "
                     f"(exit {verify.get('exit_code')}, "
                     f"{verify.get('hard_gaps')} hard gap(s)).")
    else:
        parts.append("No GhostVerify report was provided, so no Verify "
                     "check is cited in this review.")
    if scope.get("present"):
        # Count reason ENTRIES as recorded (the same reason recorded
        # for two files is two entries); the pre-polish count used
        # the de-duplicated set and under-reported the pack.
        n = scope.get("risk_reason_entries")
        if n is None:
            n = len(scope.get("risk_reasons") or [])
        parts.append(f"A GhostScope pack was provided for this change"
                     + (f" with {n} risk reason(s) recorded in scope.json."
                        if n else "."))
    parts.append(f"Verdict: {verdict}.")
    return " ".join(parts)
