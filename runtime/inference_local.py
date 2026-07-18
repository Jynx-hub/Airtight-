"""Airtight runtime — the ONE doorway to the model (`inference.local`).

Every model interaction in Airtight goes through `chat()` here. Nothing calls the
endpoint directly. That is the whole design invariant: one operator-pinned hop, so
HiddenLayer (Lane B) and OpenShell both enforce on the same place.

Two rules this file exists to keep:
  1. The endpoint is chosen by the OPERATOR (env), never by the agent. There is no
     parameter to point this somewhere else — that is deliberate.
  2. Reasoning is OFF by default (deterministic tool calls); turn it ON only for
     free-text drafting (claim writing, loophole analysis).
"""
from __future__ import annotations

import os
from typing import Any

from openai import OpenAI

try:
    from dotenv import load_dotenv

    load_dotenv(os.path.join(os.path.dirname(__file__), ".env"))
except ImportError:
    pass

# ── Backend selection (the "one env flip") ────────────────────────────────────
# INFERENCE_BACKEND is the ONLY var an operator flips to swap backends:
#
#   unset  -> LEGACY:   the flat INFERENCE_* vars, read exactly as before F3.
#   modal  -> PRIMARY:  self-hosted vLLM on Modal. The judged path — the one that
#                       earns the $500 vLLM bounty.
#   nim    -> FALLBACK: NVIDIA's free hosted endpoint. Always warm, but HOSTED, so
#                       it does NOT count toward the bounty. Break-glass only.
#
# NIM's URL and model slug are public constants, not operator choices — only the key
# comes from env. That is what makes this ONE variable instead of three, and it means
# the flip works against an otherwise-unmodified .env. The old three-var flip clobbered
# INFERENCE_API_KEY with the nvapi key, so flipping back meant re-pasting by hand.
#
# There is deliberately NO automatic failover. A silent hop to a hosted endpoint
# mid-demo would swap the judged self-hosted path for one that earns nothing and
# quietly void the bounty evidence. Falling back is an operator act.
_NIM_BASE_URL = "https://integrate.api.nvidia.com/v1"
_NIM_MODEL = "nvidia/nemotron-3-nano-30b-a3b"


def _resolve() -> tuple[str, str, str]:
    """Operator-pinned (base_url, model, api_key) for the selected backend.

    Env only. No argument, no per-call override — the agent must never be able to
    reach this. Each backend falls back to the flat INFERENCE_* vars, so a
    half-configured .env still works.
    """
    backend = os.environ.get("INFERENCE_BACKEND", "").strip().lower()
    url = os.environ.get("INFERENCE_BASE_URL", "http://localhost:8000/v1")
    model = os.environ.get("INFERENCE_MODEL", "nemotron")  # matches serve `--served-model-name`
    key = os.environ.get("INFERENCE_API_KEY", "airtight-local")

    if not backend:
        return url, model, key  # legacy path — identical to pre-F3
    if backend == "gateway":
        # A4 / F5: the agent talks ONLY to the host-side inference.local gateway
        # (runtime/inference_gateway.py). The provider credential lives in the
        # gateway's env, never here — so the sandbox .env carries a dummy token and
        # no MODAL_/NVIDIA_ key at all. The gateway strips this token and injects the
        # real one host-side. Operator-set like every other backend; the agent cannot
        # repoint INFERENCE_GATEWAY_URL any more than it can pick a model endpoint.
        return (
            os.environ.get("INFERENCE_GATEWAY_URL", "http://inference.local/v1"),
            os.environ.get("INFERENCE_MODEL", model),
            os.environ.get("INFERENCE_API_KEY", "sandbox-no-cred"),  # dummy; real key is host-side
        )
    if backend == "modal":
        return (
            os.environ.get("MODAL_BASE_URL", url),
            os.environ.get("MODAL_MODEL", model),
            os.environ.get("MODAL_API_KEY", key),
        )
    if backend == "nim":
        nim_key = os.environ.get("NVIDIA_API_KEY", "")
        if not nim_key:
            raise RuntimeError(
                "INFERENCE_BACKEND=nim but NVIDIA_API_KEY is empty. Free `nvapi-...` key "
                "at https://build.nvidia.com (no card); put it in runtime/.env."
            )
        return (
            os.environ.get("NIM_BASE_URL", _NIM_BASE_URL),
            os.environ.get("NIM_MODEL", _NIM_MODEL),
            nim_key,
        )
    raise RuntimeError(f"Unknown INFERENCE_BACKEND={backend!r} (expected: modal | nim | gateway)")


# Resolved at import so these stay readable module attributes (the __main__ block and
# verify tooling read them). `chat()` re-resolves per turn and rebuilds the client only
# if the resolved triple actually moved.
_BASE_URL, _MODEL, _API_KEY = _resolve()
_client = OpenAI(base_url=_BASE_URL, api_key=_API_KEY)
_resolved = (_BASE_URL, _MODEL, _API_KEY)


def _client_for_current_env() -> tuple[OpenAI, str]:
    """(client, model) for whatever backend is pinned right now.

    Steady state is three env reads and a tuple compare. It exists so an operator
    flip lands in-process (see `reload_backend`) instead of forcing a restart mid-demo.
    """
    global _client, _resolved, _BASE_URL, _MODEL, _API_KEY
    current = _resolve()
    if current != _resolved:
        _BASE_URL, _MODEL, _API_KEY = current
        _client = OpenAI(base_url=_BASE_URL, api_key=_API_KEY)
        _resolved = current
    return _client, _MODEL


def reload_backend() -> tuple[str, str]:
    """Operator hot-reload: re-read .env, re-resolve, rebuild. Returns (base_url, model).

    The code side of "repointing the backend is a host-side config reload, not a
    redeploy" (docs/INFERENCE-LOCAL.md). OPERATOR-ONLY: nothing in `chat()` calls it and
    it takes no arguments, so the agent cannot use it to repoint anything. This is the
    ONLY place a .env edit reaches a running process — superseded by the OpenShell
    gateway at F5.
    """
    try:
        from dotenv import load_dotenv as _load

        _load(os.path.join(os.path.dirname(__file__), ".env"), override=True)
    except ImportError:
        pass
    _client_for_current_env()
    return _BASE_URL, _MODEL


# ── HiddenLayer seam (Lane B fills this in) ───────────────────────────────────
# Keep these as the single choke point. Lane B replaces the bodies with
# `client.interactions.analyze(...)` on the prompt/tool-result (inbound) and the
# response/tool-call (outbound), deriving the action from per-category `detected`
# flags. Until then they pass through so Lanes C/D can build against a live hop.
def _guard_inbound(messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return messages


def _guard_outbound(response: Any) -> Any:
    return response


def chat(
    messages: list[dict[str, Any]],
    *,
    tools: list[dict[str, Any]] | None = None,
    reasoning: bool = False,
    **kwargs: Any,
) -> Any:
    """Single entry point for a model turn against the pinned `inference.local` hop.

    reasoning=False -> capped/off thinking, for deterministic tool-call turns.
    reasoning=True  -> full thinking, for claim drafting / loophole analysis.

    With reasoning=True, budget max_tokens generously: the thinking block spends it
    first, and a tight cap returns finish_reason="length" with `content=None` and the
    whole answer stranded in `reasoning_content`.
    """
    messages = _guard_inbound(messages)
    client, model = _client_for_current_env()
    resp = client.chat.completions.create(
        model=model,
        messages=messages,
        tools=tools,
        tool_choice="auto" if tools else None,
        # Nemotron reasoning toggle rides on the served chat template. qwen3_coder
        # tool parser => Qwen3-style `enable_thinking`. Confirm on the box; swap the
        # key here if the served template names it differently.
        extra_body={"chat_template_kwargs": {"enable_thinking": reasoning}},
        **kwargs,
    )
    return _guard_outbound(resp)


if __name__ == "__main__":
    # Mirrors verify.sh from the client side. Requires a reachable endpoint.
    print(f"→ [{os.environ.get('INFERENCE_BACKEND') or 'legacy'}] {_BASE_URL}  model={_MODEL}")
    r = chat([{"role": "user", "content": "Reply with exactly: AIRTIGHT-OK"}])
    print(r.choices[0].message.content)
