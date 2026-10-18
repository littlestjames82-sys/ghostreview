"""Diff sources and optional GhostVerify / GhostScope report readers.

Local only: git is invoked as a subprocess on the local project, files
are read from disk. Nothing here writes to the project or the network.
Optional reports are cited when supplied and readable; a supplied but
unreadable report is named as such, never silently dropped and never
invented.
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path


def diff_from_file(path: str):
    if path == "-":
        return sys.stdin.read(), "stdin"
    return Path(path).read_text(encoding="utf-8", errors="replace"), f"file:{path}"


def diff_from_git(project, staged: bool = False):
    """(diff_text, source_label, notes) from the local git repo."""
    args = ["git", "-C", str(project), "diff", "--no-color"]
    label = "git:staged" if staged else "git:working-tree-vs-HEAD"
    if staged:
        args.append("--cached")
    else:
        args.append("HEAD")
    try:
        proc = subprocess.run(args, capture_output=True, text=True, timeout=60)
    except (OSError, subprocess.SubprocessError) as exc:
        return "", label, [f"could not run git diff: {exc}"]
    if proc.returncode != 0:
        detail = (proc.stderr or "").strip().splitlines()
        return "", label, ["git diff failed: " +
                           (detail[0] if detail else "not a git repository?")]
    notes = []
    try:
        proc2 = subprocess.run(
            ["git", "-C", str(project), "status", "--porcelain"],
            capture_output=True, text=True, timeout=60)
        untracked = [ln[3:] for ln in proc2.stdout.splitlines()
                     if ln.startswith("?? ")]
        if untracked:
            notes.append(f"{len(untracked)} untracked file(s) are not in "
                         "this diff and were not reviewed: " +
                         ", ".join(sorted(untracked)[:10]))
    except (OSError, subprocess.SubprocessError):
        pass
    return proc.stdout, label, notes


def load_verify_report(path):
    """Summarise a GhostVerify verify-report.json, or return an absent/
    unreadable record. Only fields GhostVerify actually writes are read:
    verdict, exit_code, gaps / soft_gaps counts, post outcome."""
    if not path:
        return {"present": False}
    p = Path(path)
    try:
        data = json.loads(p.read_text(encoding="utf-8", errors="replace"))
    except (OSError, ValueError) as exc:
        return {"present": False, "supplied": str(p),
                "unreadable": f"could not read the supplied Verify report: {exc}"}
    post = data.get("post") or {}
    return {
        "present": True,
        "path": str(p),
        "verdict": data.get("verdict"),
        "exit_code": data.get("exit_code"),
        "kind": data.get("kind"),
        "hard_gaps": len(data.get("gaps") or []),
        "soft_gaps": len(data.get("soft_gaps") or []),
        "post_verdict": post.get("verdict"),
        "post_tests_status": (post.get("tests") or {}).get("status"),
    }


def load_scope_pack(path):
    """Summarise a GhostScope pack: accepts a pack directory or the
    scope.json file itself. Reads scope.json only; builds nothing."""
    if not path:
        return {"present": False}
    p = Path(path)
    scope_file = p if p.name == "scope.json" else p / "scope.json"
    try:
        data = json.loads(scope_file.read_text(encoding="utf-8", errors="replace"))
    except (OSError, ValueError) as exc:
        return {"present": False, "supplied": str(p),
                "unreadable": f"could not read the supplied Scope pack: {exc}"}
    # Every list GhostScope writes changed files into is read:
    # changed_files, files, changed, and analysis.changed. Earlier
    # versions of this reader skipped the top-level "changed" list,
    # silently dropping any risk reasons recorded only there.
    lists: list = []
    for key in ("changed_files", "files", "changed"):
        v = data.get(key)
        if isinstance(v, list):
            lists.extend(v)
    analysis = data.get("analysis") or {}
    if isinstance(analysis, dict) and isinstance(analysis.get("changed"), list):
        lists.extend(analysis["changed"])
    risk_reasons = []
    reasons_by_file: dict = {}
    changed_files: list = []
    for entry in lists:
        if isinstance(entry, dict):
            epath = entry.get("path")
            if epath and epath not in changed_files:
                changed_files.append(epath)
            for r in entry.get("risk_reasons") or entry.get("risks") or []:
                reason = str(r)
                risk_reasons.append(reason)
                if epath:
                    bucket = reasons_by_file.setdefault(epath, [])
                    if reason not in bucket:
                        bucket.append(reason)
        elif isinstance(entry, str) and entry not in changed_files:
            changed_files.append(entry)
    return {
        "present": True,
        "path": str(p),
        "scope_file": str(scope_file),
        "base": data.get("base"),
        "head": data.get("head"),
        "changed_files": changed_files,
        "risk_reasons": sorted(set(risk_reasons)),
        "risk_reasons_by_file": reasons_by_file,
        "risk_reason_entries": sum(len(v) for v in reasons_by_file.values())
                               or len(set(risk_reasons)),
        "tokens": data.get("tokens"),
        "keys": sorted(data.keys()),
    }
