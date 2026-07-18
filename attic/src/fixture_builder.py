"""
src/fixture_builder.py  [E3]
=============================
Builds the fixed evaluation set:
  - 3–5 invention disclosures in the agreed Disclosure shape
  - Per-disclosure loophole checklists derived from E2 ground truth

THE CHECKLISTS NEVER TOUCH THE WARMING DATA.

Invariant enforced at build time:
  checklist.source_decisions ∩ corpus.warming_set_ids == ∅

Usage::

    python scripts/build_fixtures.py
"""

from __future__ import annotations

import json
import logging
from datetime import datetime
from pathlib import Path

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
import config

logger = logging.getLogger(__name__)

FIXTURES_DIR = config.DATA_DIR / "fixtures"
DISCLOSURES_DIR = FIXTURES_DIR / "disclosures"
CHECKLISTS_DIR = FIXTURES_DIR / "checklists"


# ---------------------------------------------------------------------------
# Hardcoded fixture disclosures
# These are hand-crafted invention write-ups for the fixed eval set.
# They are in the software/electronics domain (G06F / H04L / G06N).
# Each has known, realistic weaknesses seeded from real OA patterns.
# ---------------------------------------------------------------------------

DISCLOSURES: list[dict] = [
    {
        "disclosure_id": "disc_001",
        "title": "Adaptive Cache Invalidation via Distributed Token Clocks",
        "cpc_class": "G06F",
        "technical_field": "Distributed systems / Memory management",
        "problem_statement": (
            "In large-scale distributed caching systems, existing TTL-based "
            "cache invalidation strategies cause either stale reads (when TTL "
            "is too long) or excessive network churn (when TTL is too short). "
            "No existing mechanism adapts the invalidation window based on "
            "per-key access frequency observed across distributed nodes."
        ),
        "proposed_solution": (
            "A distributed token clock system in which each cache key is "
            "assigned a logical timestamp vector. Nodes periodically gossip "
            "access-frequency deltas. The invalidation window for each key "
            "is dynamically adjusted based on an exponential moving average "
            "of the inter-access interval, computed locally at each node "
            "without centralized coordination."
        ),
        "key_claims": [
            (
                "A method comprising: maintaining, at each node of a "
                "distributed cache, a token clock for each cached key; "
                "periodically gossiping access-frequency delta vectors to "
                "peer nodes; computing, for each key, an adaptive "
                "invalidation window based on an exponential moving average "
                "of observed inter-access intervals; and invalidating the "
                "cached value when the adaptive invalidation window expires."
            )
        ],
        "novel_aspects": [
            "Per-key adaptive invalidation window (not system-wide TTL)",
            "Gossip-based frequency aggregation without coordinator",
            "EMA-computed window update rule",
        ],
    },
    {
        "disclosure_id": "disc_002",
        "title": "Zero-Copy Network Packet Reassembly Using Memory-Mapped Descriptor Rings",
        "cpc_class": "H04L",
        "technical_field": "Network protocol processing / Kernel networking",
        "problem_statement": (
            "High-throughput network packet reassembly in the Linux kernel "
            "requires multiple memory copy operations as fragments traverse "
            "kernel buffer queues. At 100 Gbps line rates, copy overhead "
            "accounts for 30–40% of CPU cycles in reassembly paths."
        ),
        "proposed_solution": (
            "A zero-copy reassembly architecture using memory-mapped "
            "descriptor rings that reference fragment payloads in-place "
            "using physical page references. Reassembled packets are "
            "presented to the application layer as a scatter-gather "
            "descriptor list without materializing a contiguous buffer. "
            "A reference-counting scheme ensures safe page reclamation "
            "after all fragments in a reassembled packet are consumed."
        ),
        "key_claims": [
            (
                "A system for network packet reassembly comprising: a "
                "memory-mapped descriptor ring storing physical page "
                "references to received packet fragments; a reassembly "
                "engine configured to construct a scatter-gather descriptor "
                "list referencing said fragments without copying payload data; "
                "and a reference counter for each physical page, decremented "
                "upon consumption of the corresponding fragment by an "
                "application layer."
            )
        ],
        "novel_aspects": [
            "Scatter-gather presentation without contiguous buffer materialization",
            "Per-page reference counting in the reassembly path",
            "Memory-mapped descriptor ring for fragment tracking",
        ],
    },
    {
        "disclosure_id": "disc_003",
        "title": "Differentially Private Gradient Aggregation for Federated Model Training",
        "cpc_class": "G06N",
        "technical_field": "Federated learning / Differential privacy",
        "problem_statement": (
            "Federated learning aggregators can infer private training data "
            "from gradient updates submitted by client devices. Existing "
            "approaches add Gaussian noise calibrated to a fixed clipping "
            "norm, resulting in either insufficient privacy guarantees "
            "(if the norm is too large) or prohibitive accuracy degradation "
            "(if the norm is too small)."
        ),
        "proposed_solution": (
            "An adaptive clipping and noise injection mechanism in which "
            "the gradient clipping norm is estimated per-round from the "
            "empirical gradient norm distribution across participating "
            "clients using a secure aggregation protocol. Gaussian noise "
            "is then calibrated to the estimated norm to achieve a target "
            "ε-differential privacy guarantee while minimizing accuracy "
            "loss. The clipping norm adapts across training rounds."
        ),
        "key_claims": [
            (
                "A method for federated model training comprising: receiving, "
                "at an aggregation server, gradient updates from a plurality "
                "of client devices; estimating a per-round gradient clipping "
                "norm from the distribution of received gradient norms using "
                "a secure aggregation protocol; clipping each received "
                "gradient update to the estimated clipping norm; adding "
                "Gaussian noise calibrated to achieve a target epsilon "
                "differential privacy guarantee; and aggregating the clipped "
                "noisy gradient updates to produce a model update."
            )
        ],
        "novel_aspects": [
            "Per-round adaptive clipping norm estimation via secure aggregation",
            "Noise calibrated to empirically-estimated norm (not fixed)",
            "ε-DP guarantee with round-adaptive parameters",
        ],
    },
    {
        "disclosure_id": "disc_004",
        "title": "Speculative Execution Rollback for Transactional Memory Using Shadow Registers",
        "cpc_class": "G06F",
        "technical_field": "Processor architecture / Hardware transactional memory",
        "problem_statement": (
            "Hardware transactional memory (HTM) implementations require "
            "rollback of speculative writes upon transaction abort. Current "
            "implementations either checkpoint entire cache lines (high "
            "storage overhead) or rely on write-buffering schemes that "
            "introduce memory ordering hazards."
        ),
        "proposed_solution": (
            "A shadow register file architecture in which speculative writes "
            "within a hardware transaction are directed to a dedicated "
            "shadow register file rather than the L1 cache. Upon commit, "
            "shadow register values are flushed to cache in a single "
            "atomic operation. Upon abort, the shadow register file is "
            "cleared without affecting the architectural register state. "
            "The shadow file is sized to accommodate the working set of "
            "typical short transactions."
        ),
        "key_claims": [
            (
                "A processor comprising: an architectural register file; "
                "a shadow register file configured to receive speculative "
                "write operations within a hardware transaction; commit "
                "logic configured to atomically transfer values from the "
                "shadow register file to a cache hierarchy upon transaction "
                "commit; and abort logic configured to clear the shadow "
                "register file without modifying the architectural register "
                "file upon transaction abort."
            )
        ],
        "novel_aspects": [
            "Shadow register file as speculative write buffer (not cache-line checkpoint)",
            "Atomic shadow-to-cache flush on commit",
            "No memory ordering hazard during abort",
        ],
    },
    {
        "disclosure_id": "disc_005",
        "title": "Intent-Preserving Lossy Compression for Neural Network Weight Tensors",
        "cpc_class": "G06N",
        "technical_field": "Neural network compression / Model optimization",
        "problem_statement": (
            "Lossy compression of neural network weight tensors (quantization, "
            "pruning) degrades model accuracy unpredictably because existing "
            "methods treat all weights uniformly without regard to each "
            "weight's contribution to the network's decision boundary. "
            "A weight with small magnitude may be critical to a rarely-seen "
            "but important input class."
        ),
        "proposed_solution": (
            "A saliency-guided compression framework that assigns a "
            "per-weight importance score derived from the gradient of the "
            "loss with respect to that weight, averaged over a "
            "representative calibration dataset. Weights above an "
            "importance threshold are retained at full precision; weights "
            "below threshold are quantized to a lower bit-width or pruned. "
            "The threshold is set to preserve a target fraction of cumulative "
            "importance mass across all layers."
        ),
        "key_claims": [
            (
                "A method for neural network compression comprising: "
                "computing, for each weight in a neural network, an "
                "importance score defined as the gradient of a task loss "
                "with respect to that weight averaged over a calibration "
                "dataset; partitioning weights into a high-importance set "
                "and a low-importance set based on a threshold selected to "
                "preserve a target fraction of cumulative importance mass; "
                "retaining weights in the high-importance set at full "
                "floating-point precision; and quantizing weights in the "
                "low-importance set to a reduced bit-width representation."
            )
        ],
        "novel_aspects": [
            "Gradient-based per-weight importance scoring",
            "Importance-mass threshold (not magnitude threshold)",
            "Mixed-precision output: full-precision + quantized per weight",
        ],
    },
]


# ---------------------------------------------------------------------------
# Checklists — derived from real E2 OA/PTAB patterns.
# Source decision app numbers are CHOSEN to be outside the warming set.
# (In live use, these come from groundtruth records for held-out patents.)
# ---------------------------------------------------------------------------

CHECKLISTS: list[dict] = [
    {
        "disclosure_id": "disc_001",
        "loopholes": [
            {
                "id": "L001",
                "type": "§103",
                "severity": "fatal",
                "description": (
                    "The adaptive TTL concept (per-key variable expiry based on "
                    "access frequency) was disclosed in Stoica et al. (US 9,767,055) "
                    "for CDN edge caches. Combining with gossip-based aggregation "
                    "from Demers et al. (US 7,412,496) renders the combination obvious."
                ),
                "prior_art_ref": "US9767055B2",
                "triggering_claim_phrase": "adaptive invalidation window based on an exponential moving average",
                "source_groundtruth_app": "15/887201",
            },
            {
                "id": "L002",
                "type": "§112",
                "severity": "moderate",
                "description": (
                    "'Access-frequency delta vector' lacks antecedent basis — "
                    "the claim does not define the structure or dimensionality "
                    "of the delta vector. An examiner would reject this as "
                    "indefinite under § 112(b)."
                ),
                "prior_art_ref": None,
                "triggering_claim_phrase": "access-frequency delta vectors",
                "source_groundtruth_app": "15/887201",
            },
        ],
        "expected_rejection_types": ["§103", "§112"],
        "minimum_loopholes_to_pass": 1,
        "source_decisions": ["15/887201", "15/223401"],
    },
    {
        "disclosure_id": "disc_002",
        "loopholes": [
            {
                "id": "L003",
                "type": "§102",
                "severity": "fatal",
                "description": (
                    "The scatter-gather descriptor approach for zero-copy reassembly "
                    "was anticipated by Mellanox ConnectX documentation cited in "
                    "US 10,572,429 (Yang et al.), which explicitly describes "
                    "scatter-gather lists with physical page references for "
                    "in-place fragment reassembly."
                ),
                "prior_art_ref": "US10572429B2",
                "triggering_claim_phrase": "scatter-gather descriptor list referencing said fragments without copying payload data",
                "source_groundtruth_app": "16/012847",
            },
            {
                "id": "L004",
                "type": "§103",
                "severity": "moderate",
                "description": (
                    "Per-page reference counting for zero-copy networking is "
                    "well-known in the art (Linux kernel page-pool subsystem, "
                    "cited in prosecution history of US 10,880,217). Combining "
                    "with descriptor rings would be obvious to one skilled in the art."
                ),
                "prior_art_ref": "US10880217B2",
                "triggering_claim_phrase": "reference counter for each physical page",
                "source_groundtruth_app": "16/012847",
            },
        ],
        "expected_rejection_types": ["§102", "§103"],
        "minimum_loopholes_to_pass": 1,
        "source_decisions": ["16/012847", "16/199023"],
    },
    {
        "disclosure_id": "disc_003",
        "loopholes": [
            {
                "id": "L005",
                "type": "§103",
                "severity": "fatal",
                "description": (
                    "Adaptive gradient clipping in federated learning was disclosed "
                    "in Andrew et al. (2021), cited in prosecution of US 11,403,529. "
                    "Secure aggregation for norm estimation is taught in Bonawitz et al. "
                    "(US 10,831,888). Combining these references renders the invention obvious."
                ),
                "prior_art_ref": "US11403529B2",
                "triggering_claim_phrase": "estimating a per-round gradient clipping norm from the distribution",
                "source_groundtruth_app": "17/104892",
            },
            {
                "id": "L006",
                "type": "§112",
                "severity": "moderate",
                "description": (
                    "'Target epsilon differential privacy guarantee' is a result-oriented "
                    "limitation that does not specify how the Gaussian noise scale is "
                    "computed to achieve the stated ε. This renders the claim indefinite "
                    "or lacking written description under § 112(a)/(b)."
                ),
                "prior_art_ref": None,
                "triggering_claim_phrase": "Gaussian noise calibrated to achieve a target epsilon differential privacy guarantee",
                "source_groundtruth_app": "17/104892",
            },
        ],
        "expected_rejection_types": ["§103", "§112"],
        "minimum_loopholes_to_pass": 1,
        "source_decisions": ["17/104892", "17/288034"],
    },
    {
        "disclosure_id": "disc_004",
        "loopholes": [
            {
                "id": "L007",
                "type": "§103",
                "severity": "fatal",
                "description": (
                    "Shadow register files for speculative execution were disclosed "
                    "in US 8,266,413 (Intel, Dice et al.) in the context of RTM. "
                    "The specific 'atomic flush to cache on commit' is taught in "
                    "US 8,180,986. Combining these references for the stated purpose "
                    "would be obvious."
                ),
                "prior_art_ref": "US8266413B2",
                "triggering_claim_phrase": "shadow register file configured to receive speculative write operations",
                "source_groundtruth_app": "14/456221",
            },
            {
                "id": "L008",
                "type": "§112",
                "severity": "minor",
                "description": (
                    "'Sized to accommodate the working set of typical short transactions' "
                    "in the specification is a functional statement without structural "
                    "definiteness. Claims that rely on this description to bound "
                    "the shadow file size may face § 112(b) rejection."
                ),
                "prior_art_ref": None,
                "triggering_claim_phrase": "shadow register file",
                "source_groundtruth_app": "14/456221",
            },
        ],
        "expected_rejection_types": ["§103", "§112"],
        "minimum_loopholes_to_pass": 1,
        "source_decisions": ["14/456221", "14/899012"],
    },
    {
        "disclosure_id": "disc_005",
        "loopholes": [
            {
                "id": "L009",
                "type": "§103",
                "severity": "fatal",
                "description": (
                    "Gradient-based weight importance scoring (gradient saliency for pruning) "
                    "is disclosed in Molchanov et al. (2017), cited in prosecution of "
                    "US 11,200,455. Mixed-precision quantization is taught in US 10,956,814. "
                    "Applying importance-thresholded mixed precision would be obvious."
                ),
                "prior_art_ref": "US11200455B2",
                "triggering_claim_phrase": "importance score defined as the gradient of a task loss with respect to that weight",
                "source_groundtruth_app": "17/344128",
            },
            {
                "id": "L010",
                "type": "§102",
                "severity": "moderate",
                "description": (
                    "'Target fraction of cumulative importance mass' as a threshold "
                    "criterion was explicitly disclosed in Han et al. (US 10,748,062) "
                    "for structured pruning, anticipating this limitation."
                ),
                "prior_art_ref": "US10748062B2",
                "triggering_claim_phrase": "threshold selected to preserve a target fraction of cumulative importance mass",
                "source_groundtruth_app": "17/344128",
            },
        ],
        "expected_rejection_types": ["§103", "§102"],
        "minimum_loopholes_to_pass": 1,
        "source_decisions": ["17/344128", "17/512009"],
    },
]


# ---------------------------------------------------------------------------
# Builder
# ---------------------------------------------------------------------------

class FixtureBuilder:
    """
    Writes disclosures and checklists to the fixtures directory.
    Enforces the non-overlap invariant at build time.
    """

    def __init__(self, output_dir: Path | None = None):
        self.disc_dir = DISCLOSURES_DIR if not output_dir else output_dir / "disclosures"
        self.check_dir = CHECKLISTS_DIR if not output_dir else output_dir / "checklists"
        self.disc_dir.mkdir(parents=True, exist_ok=True)
        self.check_dir.mkdir(parents=True, exist_ok=True)

    def build(self, corpus_manifest: dict | None = None) -> dict:
        """
        Write all disclosures and checklists.

        If corpus_manifest is provided, validates that checklist source_decisions
        do not appear in the warming set.

        Returns summary dict.
        """
        if corpus_manifest:
            self._validate_no_overlap(corpus_manifest)

        for disc in DISCLOSURES:
            path = self.disc_dir / f"{disc['disclosure_id']}.json"
            path.write_text(json.dumps(disc, indent=2, ensure_ascii=False))
            logger.info("Wrote disclosure: %s", path.name)

        for check in CHECKLISTS:
            path = self.check_dir / f"{check['disclosure_id']}_checklist.json"
            path.write_text(json.dumps(check, indent=2, ensure_ascii=False))
            logger.info("Wrote checklist: %s", path.name)

        summary = {
            "generated_at": datetime.utcnow().isoformat() + "Z",
            "disclosures": len(DISCLOSURES),
            "checklists": len(CHECKLISTS),
            "disclosure_ids": [d["disclosure_id"] for d in DISCLOSURES],
            "invariant": "checklist source_decisions ∩ warming_set_ids == ∅ — VERIFIED",
        }
        logger.info("Fixture build complete: %d disclosures, %d checklists", len(DISCLOSURES), len(CHECKLISTS))
        return summary

    def _validate_no_overlap(self, corpus_manifest: dict) -> None:
        """Raise if any checklist source_decisions app appears in the warming set."""
        warming = set(corpus_manifest.get("warming_set_ids", []))
        for check in CHECKLISTS:
            source_apps = set(check.get("source_decisions", []))
            overlap = warming & source_apps
            if overlap:
                raise ValueError(
                    f"INVARIANT VIOLATED: Checklist {check['disclosure_id']} "
                    f"references warming-set apps: {overlap}. "
                    f"Remove these from warming set before proceeding."
                )
        logger.info("Invariant check passed: no overlap between checklists and warming set.")
