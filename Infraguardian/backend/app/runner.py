from __future__ import annotations
from pathlib import Path
import json, os, shutil, subprocess
from typing import Dict, Any

CmdResult = Dict[str, Any]

def _which(name: str) -> bool:
    return shutil.which(name) is not None

def _run(cmd: list[str], cwd: Path, env: dict | None = None) -> CmdResult:
    try:
        proc = subprocess.run(
            cmd, cwd=str(cwd), env=env or os.environ.copy(),
            stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            text=True, check=False
        )
        return {"ok": proc.returncode == 0, "code": proc.returncode,
                "stdout": proc.stdout, "stderr": proc.stderr, "cmd": cmd}
    except Exception as e:
        return {"ok": False, "code": -1, "stdout": "", "stderr": str(e), "cmd": cmd}

def terraform_plan(repo: Path) -> CmdResult:
    if not _which("terraform"):
        return {"ok": False, "stderr": "terraform not found"}
    init = _run(["terraform", "init", "-backend=false"], cwd=repo)
    if not init.get("ok"): return init
    plan = _run(["terraform", "plan", "-no-color", "-out", "tf.plan"], cwd=repo)
    if not plan.get("ok"): return plan
    show = _run(["terraform", "show", "-json", "tf.plan"], cwd=repo)
    return {"ok": show.get("ok", False), "json": _safe_json(show.get("stdout", "")), "raw": show}

def tfsec_scan(repo: Path) -> CmdResult:
    if not _which("tfsec"):
        return {"ok": False, "stderr": "tfsec not found"}
    res = _run(["tfsec", "--format", "json", "--no-color", "."], cwd=repo)
    return {"ok": res.get("ok", False), "json": _safe_json(res.get("stdout", "")), "raw": res}

def checkov_scan(repo: Path) -> CmdResult:
    if not _which("checkov"):
        return {"ok": False, "stderr": "checkov not found"}
    res = _run(["checkov", "-d", ".", "-o", "json"], cwd=repo)
    return {"ok": res.get("ok", False), "json": _safe_json(res.get("stdout", "")), "raw": res}

def infracost_breakdown(repo: Path) -> CmdResult:
    if not _which("infracost"):
        return {"ok": False, "stderr": "infracost not found"}
    res = _run(["infracost", "breakdown", "--path", ".", "--format", "json"], cwd=repo)
    return {"ok": res.get("ok", False), "json": _safe_json(res.get("stdout", "")), "raw": res}

def aggregate(results: Dict[str, CmdResult]) -> Dict[str, Any]:
    agg: Dict[str, Any] = {"warnings": []}

    # tfsec
    tfsec = results.get("tfsec", {})
    tfsec_findings = []
    if tfsec.get("json"):
        tfj = tfsec["json"]
        tfsec_findings = tfj.get("results", []) if isinstance(tfj, dict) else []
    elif tfsec.get("stderr"):
        agg["warnings"].append(f"tfsec: {tfsec['stderr']}")

    # checkov
    checkov = results.get("checkov", {})
    checkov_findings = []
    if checkov.get("json"):
        cj = checkov["json"]
        if isinstance(cj, list):
            for fw in cj:
                checkov_findings += fw.get("results", {}).get("failed_checks", [])
        elif isinstance(cj, dict):
            checkov_findings += cj.get("results", {}).get("failed_checks", [])
    elif checkov.get("stderr"):
        agg["warnings"].append(f"checkov: {checkov['stderr']}")

    # infracost
    infr = results.get("infracost", {})
    total_monthly = None
    if infr.get("json") and isinstance(infr["json"], dict):
        projects = infr["json"].get("projects", [])
        for p in projects:
            s = p.get("summary", {})
            if s.get("totalMonthlyCost") is not None:
                try:
                    val = float(s["totalMonthlyCost"])
                    total_monthly = val if total_monthly is None else total_monthly + val
                except Exception:
                    pass
    elif infr.get("stderr"):
        agg["warnings"].append(f"infracost: {infr['stderr']}")

    def sev_count(findings, sev_key: str = "severity"):
        counts = {"CRITICAL":0,"HIGH":0,"MEDIUM":0,"LOW":0,"UNKNOWN":0}
        for f in findings:
            sev = (f.get(sev_key) or f.get("severity_label") or "UNKNOWN").upper()
            if sev not in counts: sev = "UNKNOWN"
            counts[sev] += 1
        return counts

    agg["tfsec"] = {"count": len(tfsec_findings), "severities": sev_count(tfsec_findings)}
    agg["checkov"] = {"count": len(checkov_findings), "severities": sev_count(checkov_findings)}
    agg["infracost"] = {"monthly_cost": total_monthly}

    agg["top_tfsec"] = [
        {"rule": f.get("rule_id"), "severity": f.get("severity"), "resource": f.get("resource")}
        for f in tfsec_findings[:5]
    ]
    agg["top_checkov"] = [
        {"check_id": f.get("check_id"), "severity": f.get("severity"), "resource": f.get("resource")}
        for f in checkov_findings[:5]
    ]
    return agg

def _safe_json(s: str):
    try:
        return json.loads(s)
    except Exception:
        return None