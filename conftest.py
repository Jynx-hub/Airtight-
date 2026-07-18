"""Put the repo root on sys.path for the test run.

The installed packages (airtight, agent, containment, surface) import via the
editable install, but `runtime/` is an operator-scripts dir that is deliberately
not packaged — yet `runtime.inference_local` / `runtime.inference_gateway` are
importable modules (run as `python -m runtime.x` from the repo root). This makes
that same namespace import resolve under pytest, without repackaging runtime/.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
