"""Single source of operator-chosen configuration.

The operator pins the model endpoint here (via environment) — never the agent,
never a call site. See docs/INFERENCE-LOCAL.md.
"""

import os

from dotenv import load_dotenv

load_dotenv()

MODE = os.getenv("AIRTIGHT_MODE", "stub")  # "stub" | "live"

# dev: Person 2's Brev vLLM URL · in-sandbox: https://inference.local/v1 · fallback: NIM cloud
BASE_URL = os.getenv("AIRTIGHT_BASE_URL", "")

API_KEY = os.getenv("AIRTIGHT_API_KEY", "dummy")  # vLLM ignores it; NIM requires a real key

# UNVERIFIED model ID — Person 2 corrects against the server's /v1/models (inference/RUNBOOK.md)
MODEL = os.getenv("AIRTIGHT_MODEL", "nvidia/nemotron-3-nano-31b-a3b")

HL_ENABLED = os.getenv("AIRTIGHT_HL_ENABLED", "false").lower() == "true"
HIDDENLAYER_API_KEY = os.getenv("HIDDENLAYER_API_KEY", "")
