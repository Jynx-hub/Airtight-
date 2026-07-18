"""Canned doorway replies for AIRTIGHT_MODE=stub — deterministic, zero network.

Lets every lane build against the real call shape before the vLLM box exists.
"""

STUB_REPLIES = {
    "tool": '{"plan": ["retrieve prior art", "draft claims", "self-critique"], "status": "all clear"}',
    # Record-shaped, so the ingest path exercises the real parse + validate route
    # offline. Reusing "tool" here would return a reply with no "pattern" key,
    # and every ingest-to-memory run on a fresh clone would silently yield zero
    # records — the write path would look wired and do nothing.
    "distill": (
        '{"pattern": "\\u00a7112 functional claiming without disclosed structure", '
        '"claim_shape": "a module configured to <function>, recited without a '
        'corresponding algorithm in the specification", '
        '"remedy": "recite the structure or algorithm that performs the function, '
        'or claim the step rather than the means"}'
    ),
    "draft": (
        "1. A method for managing a cache, comprising: receiving an access stream; "
        "computing an embedding of recent access patterns; and evicting the entry "
        "whose predicted next-access time is furthest in the future.\n"
        "2. The method of claim 1, wherein the embedding is recomputed on a fixed interval.\n"
        "[stub draft — set AIRTIGHT_MODE=live for a real model]"
    ),
}
