"""Canned doorway replies for AIRTIGHT_MODE=stub — deterministic, zero network.

Lets every lane build against the real call shape before the vLLM box exists.
"""

STUB_REPLIES = {
    "tool": '{"plan": ["retrieve prior art", "draft claims", "self-critique"], "status": "all clear"}',
    "draft": (
        "1. A method for managing a cache, comprising: receiving an access stream; "
        "computing an embedding of recent access patterns; and evicting the entry "
        "whose predicted next-access time is furthest in the future.\n"
        "2. The method of claim 1, wherein the embedding is recomputed on a fixed interval.\n"
        "[stub draft — set AIRTIGHT_MODE=live for a real model]"
    ),
}
