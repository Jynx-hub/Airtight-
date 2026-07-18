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
    ap.add_argument("--prior-art", action="store_true",
                    help="live USPTO prior-art search -> §103 loopholes for THIS invention (needs USPTO_API_KEY)")
    args = ap.parse_args()

    disclosure = Disclosure.model_validate_json(FIXTURE.read_text())
    print(f"mode={config.MODE}  model={config.MODEL}  fan_out={args.fan_out}  "
          f"episodes={args.episodes}  ingested={args.ingested}  prior_art={args.prior_art}")
    print(f"disclosure: {disclosure.id} — {disclosure.title}\n")

    # Composition is layered, so the memory sources stay orthogonal: each --flag
    # merges one more source into the store that feeds retrieval.
    store, ingested, prior_art = LoopholeStore.load(CORPUS), None, None
    if args.ingested:
        ingested = LoopholeStore.load(config.INGESTED_DIR)
        store = merged_store(store, ingested)
    if args.prior_art:
        from agent.prior_art import search_prior_art

        prior_art = LoopholeStore(search_prior_art(disclosure))
        store = merged_store(store, prior_art)

    guardrails, sink = None, None
    if args.episodes:
        from agent.episodes import CompositeStore, EpisodeStore

        episodes = EpisodeStore.load(config.EPISODES_DIR)
        store = CompositeStore(store, episodes)
        sink = episodes
    if args.episodes or args.ingested or args.prior_art:
        guardrails = store.retrieve(disclosure, k=5)
        parts = [f"{len(guardrails)} loopholes from corpus"]
        if ingested is not None:
            parts.append(f"{len(ingested)} ingested")
        if prior_art is not None:
            parts.append(f"{len(prior_art)} live prior-art")
        if sink is not None:
            parts.append(f"{len(sink)} past episodes")
        print("retrieved " + " + ".join(parts))
        for rec in guardrails:
            print(f"  {rec.id}  §{rec.statute or '?'}  {rec.pattern[:60]}")
        if args.episodes and not config.EPISODES_ENABLED:
            print("note: AIRTIGHT_EPISODES_ENABLED is false — retrieving past episodes but "
                  "NOT writing a new one this run. Set it true to compound.")

    draft = draft_patent(disclosure, guardrails=guardrails, fan_out=args.fan_out, episode_sink=sink)
    print(json.dumps(draft.model_dump(), indent=2))
    if sink is not None and config.EPISODES_ENABLED:
        print(f"\nepisode written -> {config.EPISODES_DIR}/ ({len(sink)} total) — "
              "attempt N+1 will retrieve this lesson")


if __name__ == "__main__":
    main()
