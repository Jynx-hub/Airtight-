"""Episodic memory — the "compounds" half of M3.

After a draft, the run is compressed into an Episode and persisted. On the next
run, past episodes feed retrieval alongside Person 1's warming corpus, so the
agent pre-empts loopholes it has already seen. Attempt N+1 starts smarter than N.

Isolation: this store lives OUTSIDE data/ (agent-generated, not Person 1's) and
the M4 ablation harness never references it — see agent/eval/harness.py. Writes
are opt-in (draft_patent(episode_sink=...)), so the judged run never mutates
memory. That is what keeps "empty vs warmed" a clean two-condition comparison.
"""

import re
import uuid
from datetime import datetime
from pathlib import Path

from pydantic import BaseModel, Field

from airtight import Disclosure, Draft, LoopholeRecord
from airtight.shapes import statute_of

# --- the ONE defect detector: B1's revise stop-condition and B3's distillation
# both call this, so they can never disagree. Deterministic, no model call. ---
_DEFECT_KEYWORDS = {  # keyword -> statute it implies
    "antecedent": "112", "indefinite": "112", "enablement": "112", "written description": "112",
    "means-plus-function": "112", "means plus function": "112", "overbroad": "112",
    "anticipat": "102", "obvious": "103", "abstract": "101", "eligib": "101",
    "design around": "103", "design-around": "103",
}
_BULLET_RE = re.compile(r"^\s*(?:[-*•]|\d+[.)])\s*")
DISTILL_CAP = 3  # synthetic per-run lessons must never flood the real PTAB records
_REMEDY = {
    "112": "add explicit antecedent basis and definite structure for the recited element",
    "102": "add a novel limitation the cited art does not disclose",
    "103": "add a non-obvious combination limitation with unexpected-result support",
    "101": "recite a specific technical improvement, not the abstract idea",
}


def _implied_statute(line: str) -> str:
    low = line.lower()
    return statute_of(line) or next((_DEFECT_KEYWORDS[k] for k in _DEFECT_KEYWORDS if k in low), "")


def material_defects(critique_text: str) -> list[str]:
    """Keep only lines that name a statute (§NNN) or a defect keyword. Drops
    markdown headers, 'Here are the defects:' preambles, and bare bullets — the
    junk that would otherwise become memory records or falsely keep the revise
    loop spinning. Deterministic string ops only."""
    out = []
    for raw in critique_text.splitlines():
        line = _BULLET_RE.sub("", raw.strip())
        if not line or line.startswith("#"):
            continue
        if _implied_statute(line):
            out.append(line)
    return out


class Episode(BaseModel):
    """One compressed drafting run. Agent-internal — deliberately NOT in
    airtight/shapes.py (that file is the frozen cross-lane contract)."""

    id: str
    disclosure_id: str
    technology_class: str
    retrieved_ids: list[str]  # loopholes used this run
    critique_findings: list[str]  # from Draft.critique_notes
    distilled: list[LoopholeRecord]  # lessons fed back into future retrieval
    human_correction: str | None = None
    mode: str  # "stub" | "live"
    created_at: str


def compress_run(
    disclosure: Disclosure,
    retrieved: list[LoopholeRecord],
    draft: Draft,
    mode: str,
    human_correction: str | None = None,
) -> Episode:
    """Distill a finished run into an Episode. Lessons = the retrieved loopholes
    the draft engaged, plus a BOUNDED, CLEANED set of real defects the examiner
    found (material lines only, capped) — so next-run retrieval surfaces this
    run's mistakes without markdown headers or preambles poisoning the corpus."""
    distilled = list(retrieved)
    findings = material_defects("\n".join(draft.critique_notes))[:DISTILL_CAP]
    for i, line in enumerate(findings):
        st = _implied_statute(line)  # non-empty: material_defects only kept statute-bearing lines
        m = re.search(r"claim\s+(\d+)", line.lower())
        distilled.append(
            LoopholeRecord(
                id=f"ep-{disclosure.id}-{st}-{i}",
                pattern=f"§{st} — {line[:110]}",  # §NNN in pattern -> validator derives .statute
                claim_shape=f"claim {m.group(1)} of {disclosure.id} draft" if m else f"{disclosure.id} draft",
                technology_class=disclosure.technology_class,
                remedy=_REMEDY[st],
                source=f"episode:{disclosure.id}",
            )
        )
    return Episode(
        id=f"ep-{disclosure.id}-{uuid.uuid4().hex[:8]}",
        disclosure_id=disclosure.id,
        technology_class=disclosure.technology_class,
        retrieved_ids=[r.id for r in retrieved],
        critique_findings=list(draft.critique_notes),
        distilled=distilled,
        human_correction=human_correction,
        mode=mode,
        created_at=datetime.now().astimezone().isoformat(timespec="seconds"),
    )


class EpisodeStore:
    def __init__(self, episodes: list[Episode], directory: Path | None = None):
        self.episodes = episodes
        self.directory = Path(directory) if directory else None

    @classmethod
    def load(cls, directory: Path | str) -> "EpisodeStore":
        directory = Path(directory)
        # rglob (not glob) is intentional: record() writes to <disc_id>/ subdirs,
        # unlike LoopholeStore's flat corpus dir. Different layouts on purpose.
        episodes = [
            Episode.model_validate_json(p.read_text())
            for p in sorted(directory.rglob("*.json"))
        ]
        return cls(episodes, directory)

    def record(self, episode: Episode) -> Path:
        if self.directory is None:
            raise RuntimeError("EpisodeStore has no directory to persist to")
        dest = self.directory / episode.disclosure_id
        dest.mkdir(parents=True, exist_ok=True)
        path = dest / f"{episode.created_at.replace(':', '')}-{episode.id}.json"
        path.write_text(episode.model_dump_json(indent=2))
        self.episodes.append(episode)
        return path

    def _lessons(self, live_only: bool) -> list[LoopholeRecord]:
        records: list[LoopholeRecord] = []
        for ep in self.episodes:
            if live_only and ep.mode != "live":
                continue  # a live agent won't trust stub-generated lessons
            records.extend(ep.distilled)
        return records

    def retrieve(self, disclosure: Disclosure, k: int = 5, live_only: bool = False) -> list[LoopholeRecord]:
        return _rank(self._lessons(live_only), disclosure, k)

    def __len__(self) -> int:
        return len(self.episodes)


class CompositeStore:
    """Warming corpus + accumulated episodes behind one retrieve()."""

    def __init__(self, base, episodes: EpisodeStore, live_only: bool = False):
        self.base = base
        self.episodes = episodes
        self.live_only = live_only

    def retrieve(self, disclosure: Disclosure, k: int = 5) -> list[LoopholeRecord]:
        merged: dict[str, LoopholeRecord] = {}
        for rec in list(self.base.records) + self.episodes._lessons(self.live_only):
            merged.setdefault(rec.id, rec)  # dedup by id, base wins
        return _rank(list(merged.values()), disclosure, k)

    def __len__(self) -> int:
        return len(self.base) + len(self.episodes)


def _rank(records: list[LoopholeRecord], disclosure: Disclosure, k: int) -> list[LoopholeRecord]:
    """Statute-aware retrieval, shared with LoopholeStore so the episodic and
    warming paths rank identically (class → overlap, then statute-diversified)."""
    from agent.memory import _retrieve

    return _retrieve(records, disclosure, k)
