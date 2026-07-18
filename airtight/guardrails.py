"""M2: the HiddenLayer guardrails bus. Every interaction type crosses this module.

No other file may import hiddenlayer — the single SDK touchpoint is
_raw_analyze(), and tests exercise all policy logic by monkeypatching it.
API ground truth: research/hiddenlayer.md (no scalar verdict — the action is
derived from per-category analysis[].detected flags).

Fail modes per docs/ARCHITECTURE.md Claim 2: fail-closed ONLY on the
tool_call and ingested_document hops; everything else fails open (logged).
"""

import json
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from functools import wraps
from pathlib import Path

from . import config


class Hop(str, Enum):
    USER_PROMPT = "user_prompt"  # phase: input
    MODEL_RESPONSE = "model_response"  # phase: output
    TOOL_CALL = "tool_call"  # phase: input
    TOOL_RESULT = "tool_result"  # phase: input
    INGESTED_DOCUMENT = "ingested_document"  # phase: input


class Action(str, Enum):
    PASS = "pass"
    REDACT = "redact"
    QUARANTINE = "quarantine"
    BLOCK = "block"


_SEVERITY = [Action.PASS, Action.REDACT, Action.QUARANTINE, Action.BLOCK]

_PHASE = {Hop.MODEL_RESPONSE: "output"}  # every other hop analyzes as input


@dataclass
class Detection:
    category: str  # analysis[].name, e.g. "prompt_injection", "pii"
    phase: str
    detected: bool
    matches: list  # findings.matches, passed through raw — shape UNVERIFIED


@dataclass
class Verdict:
    hop: Hop
    action: Action
    text: str  # payload text post-transform (REDACT rewrites; QUARANTINE empties)
    detections: list[Detection] = field(default_factory=list)
    event_id: str | None = None
    error: str | None = None  # set when the API failed/was malformed and fail-mode applied
    mode: str = "live"  # "off" | "live"


class GuardrailBlocked(RuntimeError):
    """Fail-closed outcome: detected/errored tool_call, or errored ingest.
    Carries the context the operator-escalation message needs."""

    def __init__(self, hop: Hop, reason: str, verdict: Verdict | None = None):
        super().__init__(f"guardrails blocked {hop.value}: {reason}")
        self.hop = hop
        self.verdict = verdict


@dataclass(frozen=True)
class HopPolicy:
    actions: dict  # detected category name -> Action
    default_detected: Action  # any other detected category
    fail_action: Action  # API error / timeout / malformed response


# The response-policy table from docs/ARCHITECTURE.md Claim 2, as data.
POLICY = {
    Hop.USER_PROMPT: HopPolicy({}, Action.PASS, Action.PASS),  # detect-only; fail-open
    Hop.MODEL_RESPONSE: HopPolicy({"pii": Action.REDACT}, Action.PASS, Action.PASS),
    Hop.TOOL_CALL: HopPolicy({}, Action.BLOCK, Action.BLOCK),  # FAIL-CLOSED
    Hop.TOOL_RESULT: HopPolicy({}, Action.QUARANTINE, Action.PASS),
    Hop.INGESTED_DOCUMENT: HopPolicy({}, Action.QUARANTINE, Action.BLOCK),  # FAIL-CLOSED
}

QUARANTINE_PLACEHOLDER = "[airtight: content quarantined — see loophole report]"

# In-process logs (Person 3's surface reads the JSONL twins under results/security/).
AUDIT_LOG: list[dict] = []
QUARANTINE_LOG: list[dict] = []

_SECURITY_DIR = Path("results/security")


def _persist(name: str, record: dict) -> None:
    try:
        _SECURITY_DIR.mkdir(parents=True, exist_ok=True)
        with open(_SECURITY_DIR / f"{name}.jsonl", "a") as f:
            f.write(json.dumps(record) + "\n")
    except OSError:
        pass  # persistence is best-effort; the in-process log is authoritative


# ---------------------------------------------------------------------------
# The ONE function that touches hiddenlayer-sdk. Tests monkeypatch exactly this.
# ---------------------------------------------------------------------------

_client = None


def _raw_analyze(text: str, phase: str) -> dict:
    """Calls client.interactions.analyze() and returns the plain response dict
    {"metadata": {...}, "analysis": [...]}. Raises on any transport/API error.

    Verified against hiddenlayer-sdk 3.8.0: HiddenLayer(bearer_token=... |
    client_id/client_secret=..., environment="prod-us"|"prod-eu");
    interactions.analyze(metadata={model, requester_id}, input|output={messages},
    hl_project_id=...). Auth is OAuth2 client-credentials or a pre-minted token.
    """
    global _client
    if _client is None:
        from hiddenlayer import HiddenLayer  # lazy: HL_ENABLED=false never reaches this

        kwargs = {"environment": config.HL_ENVIRONMENT}
        if config.HL_CLIENT_ID and config.HL_CLIENT_SECRET:
            kwargs["client_id"] = config.HL_CLIENT_ID
            kwargs["client_secret"] = config.HL_CLIENT_SECRET
        elif config.HL_TOKEN:
            kwargs["bearer_token"] = config.HL_TOKEN
        _client = HiddenLayer(**kwargs)

    payload = {"messages": [{"role": "user", "content": text}]}
    call = {"metadata": {"model": config.MODEL, "requester_id": "airtight-agent"},
            "input" if phase == "input" else "output": payload}
    if config.HL_PROJECT_ID:
        call["hl_project_id"] = config.HL_PROJECT_ID
    resp = _client.interactions.analyze(**call)
    return resp.model_dump() if hasattr(resp, "model_dump") else dict(resp)


# ---------------------------------------------------------------------------
# Verdict derivation
# ---------------------------------------------------------------------------

def _parse_detections(raw: dict) -> list[Detection]:
    analysis = raw.get("analysis")
    if not isinstance(analysis, list):
        raise ValueError("malformed response: no analysis[] array")
    detections = []
    for entry in analysis:
        if not isinstance(entry, dict) or not isinstance(entry.get("detected"), bool):
            raise ValueError(f"malformed analysis entry: {entry!r}")
        detections.append(
            Detection(
                category=str(entry.get("name", "unknown")),
                phase=str(entry.get("phase", "")),
                detected=entry["detected"],
                matches=(entry.get("findings") or {}).get("matches") or [],
            )
        )
    return detections


def _derive_action(hop: Hop, detections: list[Detection]) -> Action:
    policy = POLICY[hop]
    action = Action.PASS
    for det in detections:
        if not det.detected:
            continue
        mapped = policy.actions.get(det.category, policy.default_detected)
        if _SEVERITY.index(mapped) > _SEVERITY.index(action):
            action = mapped
    return action


def _redact(text: str, detections: list[Detection], event_id: str | None) -> str:
    """BEST-EFFORT — findings.matches shape is UNVERIFIED (research caveat lives
    here only). Tiered: dict spans -> literal strings -> whole-text banner. The
    redaction marker is always visible so the transform is demonstrable."""
    redacted = text
    hit = False
    for det in detections:
        if not (det.detected and det.category == "pii"):
            continue
        for match in det.matches:
            if isinstance(match, dict) and isinstance(match.get("text"), str):
                redacted = redacted.replace(match["text"], "[REDACTED]")
                hit = True
            elif isinstance(match, str) and match in redacted:
                redacted = redacted.replace(match, "[REDACTED]")
                hit = True
    if not hit:  # unknown matches shape — fall back to replacing the whole payload
        return f"[REDACTED: pii detected — HiddenLayer event {event_id}]"
    return redacted


# ---------------------------------------------------------------------------
# Public entry points
# ---------------------------------------------------------------------------

def analyze(hop: Hop, text: str, *, source: str | None = None) -> Verdict:
    """PASS/REDACT/QUARANTINE return a Verdict; BLOCK raises GuardrailBlocked."""
    if not config.HL_ENABLED:
        return Verdict(hop=hop, action=Action.PASS, text=text, mode="off")

    try:
        raw = _raw_analyze(text, _PHASE.get(hop, "input"))
        detections = _parse_detections(raw)
        event_id = (raw.get("metadata") or {}).get("event_id")
        action = _derive_action(hop, detections)
        error = None
    except Exception as exc:  # transport error or malformed response: apply fail mode
        detections, event_id = [], None
        action = POLICY[hop].fail_action
        error = f"{type(exc).__name__}: {exc}"

    out_text = text
    if action is Action.REDACT:
        out_text = _redact(text, detections, event_id)
    elif action in (Action.QUARANTINE, Action.BLOCK):
        out_text = ""

    verdict = Verdict(hop=hop, action=action, text=out_text, detections=detections,
                      event_id=event_id, error=error)

    record = {
        "ts": datetime.now().astimezone().isoformat(timespec="seconds"),
        "hop": hop.value,
        "action": action.value,
        "source": source,
        "event_id": event_id,
        "error": error,
        "categories": [d.category for d in detections if d.detected],
    }
    AUDIT_LOG.append(record)
    _persist("audit", record)
    if action is Action.QUARANTINE:
        QUARANTINE_LOG.append(record)
        _persist("quarantine", record)
    if action is Action.BLOCK:
        _persist("escalations", record)
        raise GuardrailBlocked(hop, error or "detection", verdict)
    return verdict


def guarded_tool(fn):
    """Wrap a tool: tool_call hop on the args before execution (BLOCK raises,
    the tool never runs), tool_result hop on the return value after."""

    @wraps(fn)
    def wrapper(*args, **kwargs):
        call_repr = json.dumps({"tool": fn.__name__, "args": [str(a) for a in args],
                                "kwargs": {k: str(v) for k, v in kwargs.items()}})
        analyze(Hop.TOOL_CALL, call_repr, source=fn.__name__)
        result = fn(*args, **kwargs)
        verdict = analyze(Hop.TOOL_RESULT, str(result), source=fn.__name__)
        return QUARANTINE_PLACEHOLDER if verdict.action is Action.QUARANTINE else result

    return wrapper


def messages_text(messages: list[dict]) -> str:
    return "\n".join(str(m.get("content", "")) for m in messages)
