# Recursive Intelligence: the learning mechanism, with evidence

The track asks for a system that captures what it learns, compounds it into a persistent
knowledge base, and improves at its task over successive runs, and it gives bonus credit for a
clear learning mechanism: knowledge graph, RAG-from-self-context, or compressed episodic memory.
Airtight has all three, and they compound live. This document shows each one working, with real
output you can reproduce. It also states the honest limit: the mechanism is real; a positive
cross-run quality delta is not yet demonstrated.

## Mechanism 1: a statute-indexed failure library (RAG-from-self)

The agent mines real USPTO office actions into a persistent library of the ways patents actually
fail, indexed by statutory basis, so each new draft is written against the real failure modes for
its class rather than from the model's memory.

```
193 real office-action defects, indexed by statutory basis:
   §101: 27 records      (Alice/Mayo subject-matter eligibility)
   §102: 16 records      (anticipation)
   §103: 111 records     (obviousness)
   §112: 39 records      (indefiniteness / means-plus-function)
```

## Mechanism 2: compressed episodic memory that compounds across runs

After each run the agent distills a lesson from its own critique (`agent/episodes.py`,
`compress_run`) and writes it to a persistent store. The next run retrieves it. Memory grows,
and each run stands on the ones before it.

```
attempt 1: retrieved 5 loopholes from corpus + 0 past episodes
attempt 2: retrieved 5 loopholes from corpus + 1 past episodes
attempt 3: retrieved 5 loopholes from corpus + 2 past episodes
```

Reproduce:

```
AIRTIGHT_EPISODES_ENABLED=true python -m agent.run_smoke --episodes   # run it 3 times
```

## Mechanism 3: ingest-from-documents, behind a security gate

Admitted documents are distilled into the same store, upstream of the model, behind a HiddenLayer
quarantine gate, so the agent learns from new prior art without a poisoned document reaching the
draft.

```
memory: ing-644d1b8495b7 -> memory/ingested/  (statute §112, confidence 0.3)
```

Provenance is graded by an extraction-confidence trust gate: real PTAB records are trusted (1.0),
self-generated episodic lessons enter at 0.5, and ingested-document records at 0.3, so a lower
source can only surface by out-ranking a trusted one, never by taking a reserved slot.

## All three compound into one retrieval

A single run composes every source into one ranked context that primes the drafting turn:

```
retrieved 5 loopholes from corpus + 1 ingested + 5 live prior-art + 3 past episodes
```

The corpus is the failure library, the ingested record is document-learned, the live prior art is
fetched from USPTO for this specific invention, and the past episodes are the agent's own prior
lessons. That is RAG-from-self, episodic memory, and ingest, all feeding one draft.

## The honest limit

The mechanism is real and demonstrable. What is not yet demonstrated is that the compounding
improves output quality on a controlled measurement. The empty-vs-warmed ablation, after we fixed
a claim-parsing scoring bug that had faked a positive result, is `empty 13 / warmed 9`: warmed
memory did not beat empty. We report the number that survived the bug rather than the one that did
not. The measurement infrastructure is rigorous (byte-identical prompts across arms asserted by
`scaffold_proof`, a config fingerprint that stamps a content hash of the ranker, a blinded judge),
which is why we trust the negative. See `SUBMISSION.md` for the framing and `docs/WORKSTREAMS.md`
for the full audit trail.
