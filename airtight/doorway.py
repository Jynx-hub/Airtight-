"""The one doorway to the model.

Every inference call in Airtight goes through call_model() — no other code may
construct a model client. This is the single hop that inference.local pins,
HiddenLayer analyzes (M2), and OpenShell contains. Contract: docs/INFERENCE-LOCAL.md.
"""

from dataclasses import dataclass
from typing import Any, Iterator, Literal

from . import config
from .stubs import STUB_REPLIES

Role = Literal["tool", "draft", "distill"]


@dataclass
class ModelReply:
    text: str
    raw: Any
    mode: str  # "stub" | "live"


def _reasoning_params(role: Role) -> dict:
    # UNVERIFIED: the exact Nemotron reasoning-toggle key (chat-template kwarg vs
    # thinking-budget param) — confirm against the vLLM Nemotron 3 cookbook
    # (research/vllm.md sources) and fix HERE only.
    thinking = role == "draft"  # tool turns run deterministic, draft turns think deep
    # Verified key is `enable_thinking` (runtime/inference_local.py, docs/THROUGHPUT.md);
    # `thinking` was a no-op that left reasoning ON.
    return {"extra_body": {"chat_template_kwargs": {"enable_thinking": thinking}}}


def _analyze(hop: str, payload):
    # M2: the HiddenLayer bus. Signature frozen — called on every input/output hop.
    # HL_ENABLED=false short-circuits inside guardrails.analyze (zero network/import).
    # Streaming caveat: the output hop sees accumulated text after chunks were
    # already yielded, so REDACT is log-only for streams.
    from . import guardrails as g

    if hop == "input":
        g.analyze(g.Hop.USER_PROMPT, g.messages_text(payload))  # detect-only, fail-open
        return payload

    verdict = g.analyze(g.Hop.MODEL_RESPONSE, payload if isinstance(payload, str) else str(payload))
    return verdict.text


def _client():
    if not config.BASE_URL:
        raise RuntimeError(
            "AIRTIGHT_MODE=live but AIRTIGHT_BASE_URL is unset — the operator "
            "pins the endpoint via env (docs/INFERENCE-LOCAL.md)."
        )
    from openai import OpenAI  # imported here so stub mode never touches it

    # Explicit timeout (was inheriting the SDK default). Generous so it survives
    # an A100 cold start (~1-2 min) — a short ceiling can't, and each timed-out
    # retry wakes a scaled-down endpoint and bills. Operator-tunable.
    return OpenAI(base_url=config.BASE_URL, api_key=config.API_KEY, timeout=config.TIMEOUT_S)


def call_model(
    messages: list[dict],
    *,
    role: Role = "draft",
    stream: bool = False,
    **gen_kwargs,
) -> ModelReply | Iterator[str]:
    """Run one model turn. Returns ModelReply, or an iterator of text chunks
    when stream=True (the output hop is analyzed on the accumulated text)."""
    messages = _analyze("input", messages)

    if config.MODE == "stub":
        text = _analyze("output", STUB_REPLIES[role])  # bus transforms (e.g. REDACT) apply in stub too
        if stream:
            return iter(word + " " for word in text.split(" "))
        return ModelReply(text=text, raw={"stub": True, "role": role}, mode="stub")

    client = _client()
    # dict-literal merge (not dict(**...)) so a caller's gen_kwargs can override
    # the role defaults (e.g. extra_body) instead of raising on a duplicate key.
    params = {"model": config.MODEL, "messages": messages, **_reasoning_params(role), **gen_kwargs}

    if stream:
        def _gen() -> Iterator[str]:
            acc: list[str] = []
            for event in client.chat.completions.create(stream=True, **params):
                delta = event.choices[0].delta.content or ""
                acc.append(delta)
                yield delta
            _analyze("output", "".join(acc))

        return _gen()

    resp = client.chat.completions.create(**params)
    text = _analyze("output", resp.choices[0].message.content or "")
    return ModelReply(text=text, raw=resp, mode="live")
