# backend/app/agent_cli.py
from pathlib import Path
import sys
from typing import Any

from dotenv import load_dotenv

from app.models import AgentState, RepoContext
from app.graph import build_graph


def _to_agent_state(x: Any) -> AgentState:
    """
    LangGraph may return a dict instead of our Pydantic model.
    This helper normalizes the output to AgentState.
    """
    if isinstance(x, AgentState):
        return x
    if isinstance(x, dict):
        return AgentState(**x)
    raise TypeError(f"Unexpected graph output type: {type(x)}")


# Usage: python -m app.agent_cli <repo_dir> [diff_summary]
def main():
    load_dotenv()  # load .env if present

    if len(sys.argv) < 2:
        print("Usage: python -m app.agent_cli <repo_dir> [diff_summary]")
        sys.exit(1)

    repo_dir = sys.argv[1]
    diff_summary = sys.argv[2] if len(sys.argv) > 2 else None

    # Build initial state and run the agent graph
    state = AgentState(ctx=RepoContext(repo_dir=repo_dir, diff_summary=diff_summary))
    graph = build_graph()
    out = graph.invoke(state)

    # Normalize to AgentState (handles dict outputs)
    out_state = _to_agent_state(out)

    # Write the PR-ready Markdown report next to the repo under review
    report = Path(repo_dir) / "report_agent.md"
    md = out_state.synthesis.markdown if out_state.synthesis else "(no synthesis)"
    report.write_text(md, encoding="utf-8")
    print(f"Agent report written to {report}")


if __name__ == "__main__":
    main()