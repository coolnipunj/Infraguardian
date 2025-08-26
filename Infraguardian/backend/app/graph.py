from __future__ import annotations

import os
from pathlib import Path
from typing import Optional

from langgraph.graph import StateGraph, END
from langchain_openai import ChatOpenAI

from app.models import (
    AgentState, ReviewPlan, PlanStep, Findings, Synthesis, PatchSuggestion,
)
from app.runner import (
    terraform_plan, tfsec_scan, checkov_scan, infracost_breakdown, aggregate,
)

def _env(name: str, default: Optional[str] = None) -> Optional[str]:
    val = os.getenv(name)
    return val if val not in (None, "") else default

def _llm() -> Optional[ChatOpenAI]:
    api_key = _env("OPENAI_API_KEY")
    if not api_key:
        return None
    model_name = _env("OPENAI_MODEL", "gpt-4o-mini")
    try:
        return ChatOpenAI(model=model_name, temperature=0.1)
    except Exception:
        return None

def _shorten(text: Optional[str], max_chars: int = 4000) -> Optional[str]:
    if not text:
        return text
    return text if len(text) <= max_chars else text[:max_chars] + f"\n...[truncated {len(text) - max_chars} chars]"

def planner_node(state: AgentState) -> AgentState:
    llm = _llm()
    ctx = state.ctx
    if not llm:
        state.plan = ReviewPlan(
            steps=[
                PlanStep(tool="terraform_plan"),
                PlanStep(tool="tfsec"),
                PlanStep(tool="checkov"),
                PlanStep(tool="infracost"),
            ],
            justification="Deterministic fallback (no LLM/model unavailable).",
        )
        return state

    system_prompt = (
        "You are an Infrastructure-as-Code review planner. "
        "Given a repo diff summary and policy snippets, decide the MINIMAL set of tools to run "
        "(allowed tools: terraform_plan, tfsec, checkov, conftest, infracost, gitleaks) and any flags. "
        "Output strictly a ReviewPlan JSON matching the schema."
    )
    user_payload = {
        "diff_summary": _shorten(ctx.diff_summary, 2000),
        "policy_snippets": (ctx.policy_snippets or [])[:6],
        "tools": ["terraform_plan","tfsec","checkov","conftest","infracost","gitleaks"],
    }

    try:
        plan: ReviewPlan = llm.with_structured_output(ReviewPlan).invoke(
            [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": str(user_payload)},
            ]
        )
        if not plan.steps:
            raise ValueError("LLM returned an empty plan.")
        state.plan = plan
    except Exception as e:
        state.plan = ReviewPlan(
            steps=[
                PlanStep(tool="terraform_plan"),
                PlanStep(tool="tfsec"),
                PlanStep(tool="checkov"),
                PlanStep(tool="infracost"),
            ],
            justification=f"LLM planning failed: {e}. Using default plan.",
        )
    return state

def tools_node(state: AgentState) -> AgentState:
    repo_dir = Path(state.ctx.repo_dir).resolve()
    results = {}
    steps = state.plan.steps if state.plan else []

    ordered = sorted(steps, key=lambda s: 0 if s.tool == "terraform_plan" else 1)

    for step in ordered:
        t = step.tool
        if t == "terraform_plan":
            results["terraform"] = terraform_plan(repo_dir)
        elif t == "tfsec":
            results["tfsec"] = tfsec_scan(repo_dir)
        elif t == "checkov":
            results["checkov"] = checkov_scan(repo_dir)
        elif t == "infracost":
            results["infracost"] = infracost_breakdown(repo_dir)
        # conftest/gitleaks hooks later

    agg = aggregate(results)
    state.findings = Findings(
        tfsec=agg.get("tfsec", {}),
        checkov=agg.get("checkov", {}),
        terraform=results.get("terraform", {}),
        infracost=agg.get("infracost", {}),
        warnings=agg.get("warnings", []),
    )
    return state

def synth_node(state: AgentState) -> AgentState:
    llm = _llm()
    if not llm:
        tfsec = state.findings.tfsec
        checkov = state.findings.checkov
        cost = state.findings.infracost
        warnings = state.findings.warnings
        md = [
            "# InfraGuardian Report (deterministic)",
            f"**tfsec**: {tfsec.get('count', 0)} issues — {tfsec.get('severities', {})}",
            f"**Checkov**: {checkov.get('count', 0)} issues — {checkov.get('severities', {})}",
            f"**Estimated Monthly Cost**: {cost.get('monthly_cost', 'unavailable')}",
        ]
        if warnings:
            md.append("> Warnings: " + "; ".join(warnings))
        state.synthesis = Synthesis(markdown="\n\n".join(md))
        return state

    system_prompt = (
        "You are an expert IaC security and FinOps reviewer. "
        "Given structured findings from tools, write ONE concise Markdown report suitable for a PR comment. "
        "Include: severity rollups, a few top issues with resource IDs, CIS/NIST refs when clear, "
        "estimated monthly cost (if available), and SPECIFIC actionable fixes. "
        "Keep under ~300 lines and do not invent data."
    )
    try:
        md = llm.invoke(
            [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": str(state.findings.model_dump())},
            ]
        ).content
        state.synthesis = Synthesis(markdown=md or "(empty)")
    except Exception as e:
        state.synthesis = Synthesis(
            markdown=(
                "# InfraGuardian Report (fallback)\n\n"
                f"LLM synthesis failed: {e}\n\n"
                f"- tfsec: {state.findings.tfsec}\n"
                f"- checkov: {state.findings.checkov}\n"
                f"- cost: {state.findings.infracost}\n"
            )
        )
    return state

def patcher_node(state: AgentState) -> AgentState:
    state.patch = PatchSuggestion(
        notes="Auto-fix patch generation arrives in the next milestone."
    )
    return state

def build_graph():
    g = StateGraph(AgentState)
    g.add_node("planner", planner_node)
    g.add_node("tools", tools_node)
    g.add_node("synth", synth_node)
    g.add_node("patch", patcher_node)

    g.set_entry_point("planner")
    g.add_edge("planner", "tools")
    g.add_edge("tools", "synth")
    g.add_edge("synth", "patch")
    g.add_edge("patch", END)
    return g.compile()