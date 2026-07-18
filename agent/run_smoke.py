"""End-to-end M1 smoke: sample disclosure → work loop → printed Draft.

Green in stub mode with no network. Flip AIRTIGHT_MODE=live (plus
AIRTIGHT_BASE_URL) to exercise the real endpoint with the same command:

    python -m agent.run_smoke
"""

import json
import pathlib

from airtight import Disclosure, config
from agent.loop import draft_patent

FIXTURE = pathlib.Path(__file__).resolve().parent.parent / "data" / "fixtures" / "sample_disclosure.json"


def main() -> None:
    disclosure = Disclosure.model_validate_json(FIXTURE.read_text())
    print(f"mode={config.MODE}  model={config.MODEL}")
    print(f"disclosure: {disclosure.id} — {disclosure.title}\n")
    draft = draft_patent(disclosure)
    print(json.dumps(draft.model_dump(), indent=2))


if __name__ == "__main__":
    main()
