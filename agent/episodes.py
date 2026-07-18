"""Episodic memory — the "compounds" half of M3.

After a draft, the run is compressed into an Episode and persisted. On the next
run, past episodes feed retrieval alongside Person 1's warming corpus, so the
agent pre-empts loopholes it has already seen. Attempt N+1 starts smarter than N.

Isolation: this store lives OUTSIDE data/ (agent-generated, not Person 1's) and
the M4 ablation harness never references it — see agent/eval/harness.py. Writes
are opt-in (draft_patent(episode_sink=...)), so the judged run never mutates
memory. That is what keeps "empty vs warmed" a clean two-condition comparison.
"""

import uuid
from datetime import datetime
from pathlib import Path

from pydantic import BaseModel, Field

from airtight import Disclosure, Draft, LoopholeRecord
from agent.memory import tokens


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
    """Distill a finished run into an Episode. The distilled lessons are the
    retrieved loopholes the draft engaged plus one record per critique finding,
    so next-run retrieval can surface this run's hard-won lessons."""
    distilled = list(retrieved)
    for i, finding in enumerate(draft.critique_notes):
        distilled.append(
            LoopholeRecord(
                id=f"ep-lesson-{disclosure.id}-{i}",
                pattern=finding[:120],
                claim_shape=f"observed while drafting {disclosure.id}",
                technology_class=disclosure.technology_class,
                remedy="carry this critique forward into same-class drafts",
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
