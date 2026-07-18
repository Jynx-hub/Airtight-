"""Single source of operator-chosen configuration.

The operator pins the model endpoint here (via environment) — never the agent,
never a call site. See docs/INFERENCE-LOCAL.md.
"""

import os

from dotenv import load_dotenv

load_dotenv()

MODE = os.getenv("AIRTIGHT_MODE", "stub")  # "stub" | "live"

# dev: Person 2's Modal vLLM URL · in-sandbox: https://inference.local/v1 · fallback: NIM cloud
BASE_URL = os.getenv("AIRTIGHT_BASE_URL", "")

API_KEY = os.getenv("AIRTIGHT_API_KEY", "dummy")  # vLLM ignores it; NIM requires a real key

# UNVERIFIED model ID — Person 2 corrects against the server's /v1/models (inference/RUNBOOK.md)
MODEL = os.getenv("AIRTIGHT_MODEL", "nvidia/nemotron-3-nano-31b-a3b")

# --- HiddenLayer guardrails bus (M2) — auth is OAuth2 client-credentials, research/hiddenlayer.md §4 ---
HL_ENABLED = os.getenv("AIRTIGHT_HL_ENABLED", "false").lower() == "true"
HL_CLIENT_ID = os.getenv("HIDDENLAYER_CLIENT_ID", "")
HL_CLIENT_SECRET = os.getenv("HIDDENLAYER_CLIENT_SECRET", "")
HL_TOKEN = os.getenv("HIDDENLAYER_TOKEN", "")  # pre-minted shortcut the SDK accepts
HL_PROJECT_ID = os.getenv("HIDDENLAYER_PROJECT_ID", "")  # scopes the ruleset (hl-project-id)
HL_ENVIRONMENT = os.getenv("HIDDENLAYER_ENVIRONMENT", "prod-us")
HL_TIMEOUT_S = float(os.getenv("HIDDENLAYER_TIMEOUT_SECONDS", "10"))

# --- Episodic memory + concurrent sub-agents (M3 "compounds" + vLLM workload) ---
EPISODES_DIR = os.getenv("AIRTIGHT_EPISODES_DIR", "memory/episodes")  # agent-generated, outside data/
EPISODES_ENABLED = os.getenv("AIRTIGHT_EPISODES_ENABLED", "false").lower() == "true"
SUBAGENT_MAX_WORKERS = int(os.getenv("AIRTIGHT_SUBAGENT_MAX_WORKERS", "4"))
