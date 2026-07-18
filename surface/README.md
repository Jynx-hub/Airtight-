# surface/ — Person 3's lane

The Applicant Surface (intake → draft studio → grant + loophole report) and the demo show. Tasks D1-D6: `docs/WORKSTREAMS.md`.

Next.js app lands here (Streamlit is the faster backup). **The contract:** the backend exchanges JSON matching `airtight/shapes.py` — `Disclosure` in, `Draft` and `EvalResult` out. Build against `data/fixtures/sample_disclosure.json` and stubbed drafts first (`python -m agent.run_smoke` prints one); swap to the real agent when it's ready.
