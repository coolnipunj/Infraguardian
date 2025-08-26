from __future__ import annotations
from typing import List, Literal, Optional, Dict, Any
from pydantic import BaseModel

ToolName = Literal["terraform_plan","tfsec","checkov","conftest","infracost","gitleaks"]

class RepoContext(BaseModel):
    repo_dir: str
    diff_summary: Optional[str] = None
    policy_snippets: Optional[List[str]] = None

class PlanStep(BaseModel):
    tool: ToolName
    args: Dict[str, Any] = {}

class ReviewPlan(BaseModel):
    steps: List[PlanStep]
    justification: str

class Findings(BaseModel):
    tfsec: Dict[str, Any] = {}
    checkov: Dict[str, Any] = {}
    terraform: Dict[str, Any] = {}
    conftest: Dict[str, Any] = {}
    infracost: Dict[str, Any] = {}
    gitleaks: Dict[str, Any] = {}
    warnings: List[str] = []

class Synthesis(BaseModel):
    markdown: str
    risks_ranked: List[Dict[str, Any]] = []
    controls: List[str] = []

class PatchSuggestion(BaseModel):
    patch_unified_diff: Optional[str] = None
    notes: Optional[str] = None

class AgentState(BaseModel):
    ctx: RepoContext
    plan: Optional[ReviewPlan] = None
    findings: Findings = Findings()
    synthesis: Optional[Synthesis] = None
    patch: Optional[PatchSuggestion] = None