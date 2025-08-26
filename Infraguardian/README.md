# InfraGuardian — Agentic IaC Reviewer

Agentic PR reviewer for Terraform. Runs tfsec/Checkov/Infracost, merges results into ONE Markdown comment via LangGraph + OpenAI, and posts it to your PR.

## Quick start (local)
```bash
python -m venv .venv && source .venv/bin/activate
pip install -r backend/app/requirements.txt
export PYTHONPATH=$PWD/backend

# Optional: keys for best results
export OPENAI_API_KEY="sk-..."          # enables agent planning & synthesis
export INFRACOST_API_KEY="ic-..."       # enables cost delta

# Run agent locally against demo IaC
python -m app.agent_cli example/terraform "Demo diff: bucket + NAT count"
cat example/terraform/report_agent.md