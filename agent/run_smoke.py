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
from agent.memory import LoopholeStore

FIXTURE = pathlib.Path(__file__).resolve().parent.parent / "data" / "fixtures" / "sample_disclosure.json"
CORPUS = pathlib.Path(__file__).resolve().parent.parent / "data" / "corpus" / "loopholes"


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--fan-out", action="store_true", help="concurrent retrieval sub-agents")
    ap.add_argument("--episodes", action="store_true", help="write an episode + retrieve from past ones")
    args = ap.parse_args()

    disclosure = Disclosure.model_validate_json(FIXTURE.read_text())
    print(f"mode={config.MODE}  model={config.MODEL}  fan_out={args.fan_out}  episodes={args.episodes}")
    print(f"disclosure: {disclosure.id} — {disclosure.title}\n")

    # B2: episodic compounding turns on via the flag OR the operator env var. Before this,
    # AIRTIGHT_EPISODES_ENABLED was defined in config but read nowhere, so setting it did
    # nothing — the flag was the only real gate.
    episodes_on = args.episodes or config.EPISODES_ENABLED
    guardrails, sink = None, None
    if episodes_on:
        from agent.episodes import CompositeStore, EpisodeStore

        episodes = EpisodeStore.load(config.EPISODES_DIR)
        composite = CompositeStore(LoopholeStore.load(CORPUS), episodes)
        guardrails = composite.retrieve(disclosure, k=5)
        sink = episodes
        print(f"retrieved {len(guardrails)} loopholes from corpus + {len(episodes)} past episodes")

    draft = draft_patent(disclosure, guardrails=guardrails, fan_out=args.fan_out, episode_sink=sink)
    print(json.dumps(draft.model_dump(), indent=2))
    if sink is not None:
        print(f"\nepisode written -> {config.EPISODES_DIR}/ ({len(sink)} total)")


if __name__ == "__main__":
    main()
