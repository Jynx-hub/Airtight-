"""End-to-end M1 smoke: sample disclosure → work loop → printed Draft.

Green in stub mode with no network. Flip AIRTIGHT_MODE=live (plus
AIRTIGHT_BASE_URL) to exercise the real endpoint with the same command:

    python -m agent.run_smoke
"""

import argparse
import json
import pathlib

from airtight import Disclosure, config
from agent.loop import draft_patent
from agent.memory import LoopholeStore, merged_store

FIXTURE = pathlib.Path(__file__).resolve().parent.parent / "data" / "fixtures" / "sample_disclosure.json"
CORPUS = pathlib.Path(__file__).resolve().parent.parent / "data" / "corpus" / "loopholes"


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--fan-out", action="store_true", help="concurrent retrieval sub-agents")
    ap.add_argument("--episodes", action="store_true", help="write an episode + retrieve from past ones")
    ap.add_argument("--ingested", action="store_true",
                    help="also retrieve from records distilled at ingest (memory/ingested)")
    args = ap.parse_args()

    disclosure = Disclosure.model_validate_json(FIXTURE.read_text())
    print(f"mode={config.MODE}  model={config.MODEL}  fan_out={args.fan_out}  "
          f"episodes={args.episodes}  ingested={args.ingested}")
    print(f"disclosure: {disclosure.id} — {disclosure.title}\n")

    # Composition is layered, so the two memory sources stay orthogonal: the
    # --episodes path below is byte-identical to what it was before --ingested
    # existed when the flag is used alone.
    store, ingested = LoopholeStore.load(CORPUS), None
    if args.ingested:
        ingested = LoopholeStore.load(config.INGESTED_DIR)
        store = merged_store(store, ingested)

    guardrails, sink = None, None
    if args.episodes:
        from agent.episodes import CompositeStore, EpisodeStore

        episodes = EpisodeStore.load(config.EPISODES_DIR)
        store = CompositeStore(store, episodes)
        sink = episodes
    if args.episodes or args.ingested:
        guardrails = store.retrieve(disclosure, k=5)
        parts = [f"{len(guardrails)} loopholes from corpus"]
        if ingested is not None:
            parts.append(f"{len(ingested)} ingested")
        if sink is not None:
            parts.append(f"{len(sink)} past episodes")
        print("retrieved " + " + ".join(parts))
        for rec in guardrails:
            print(f"  {rec.id}  §{rec.statute or '?'}  {rec.pattern[:60]}")

    draft = draft_patent(disclosure, guardrails=guardrails, fan_out=args.fan_out, episode_sink=sink)
    print(json.dumps(draft.model_dump(), indent=2))
    if sink is not None:
        print(f"\nepisode written -> {config.EPISODES_DIR}/ ({len(sink)} total)")


if __name__ == "__main__":
    main()
