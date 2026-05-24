# Methodology

This document explains the *experimental shape* of the project — why graph-native unsupervised detection is the headline, how the post-hoc label-overlap number is computed, and the honest limits of what it implies. Read it after the README pitch.

## Why graph-native unsupervised detection

Three structural reasons real AML stacks need this kind of detector, not just a labeled supervised model:

1. **Label scarcity.** Confirmed laundering cases are rare, lagging, and adversarially curated. A bank may know about 10³ confirmed instances when the actual incidence is 10⁵–10⁶. Training a supervised model exclusively against confirmed labels learns the *shape of past investigations*, not the shape of current laundering.
2. **Novel typologies.** Attackers adapt. A model trained on yesterday's labels misses today's structure-only signal — accounts moving through a 3-hop ring with timestamps that line up, even though no historical case looked exactly like this one.
3. **Cold start.** A new product, new geography, or new product line starts with zero labels. Graph-native rules work from day one against the transaction stream itself.

In this project the **circular flow** and **mule hub** detectors are the unsupervised graph-native side; **laundering exposure** is the supervised control case. The point of having all three on one finding schema is that each represents a different *signal regime*, and a real AML stack composes them.

## The discipline boundary

Per the project's design contract:

- `src/assessments/circular_flow.py` MUST NOT reference `bronze.is_laundering`.
- `src/assessments/mule_hub.py` MUST NOT reference `bronze.is_laundering`.
- `src/assessments/laundering_exposure.py` is the only detector that may read the label.

This is enforced by `tests/test_invariants.py::test_graph_native_detector_does_not_read_label` — a CI failure here means someone refactored a detector and accidentally introduced a label dependency. The whole post-hoc label-overlap story collapses the moment a graph-native detector starts training on labels.

## The label-overlap measurement

The headline claim — *86 of 109 detected rings (78.9 %) have all three hops flagged in the AMLSim label, 91 of 109 (83.5 %) touch at least one labeled edge* — is a **post-hoc evaluation**, not a training signal. The numbers are recomputed every run by [`docs/calibration.md`](calibration.md), which holds the exact SQL.

How it's computed (see `assessments/circular_flow.py` and `docs/build-log.md` for SQL):

1. `circular_flow` detects 3-hop cycles over `silver.transfers_to` using **timestamp-ordered self-joins** — no label reference anywhere in the SQL.
2. After detection, a separate analysis query joins each ring's three edges back to `bronze.transactions_raw` and reads the `is_laundering` column for each constituent edge.
3. Two counts:
   - **Strict (~80%)**: rings where *every one* of the 3 hops has `is_laundering = 1` in the ground truth → "the whole structure was visible to the label."
   - **Loose (~83%)**: rings where *at least one* hop has `is_laundering = 1` → "the structure touches the label-known set."

The detector never sees the label. The label is consulted only to score *the detector's existing output*. There is no train-time leakage because there is no training — the detector is deterministic SQL with fixed thresholds.

## What ~80% does and does not imply

**It does imply:**
- Graph structure alone is sufficient signal to recover a large fraction of the label-known laundering set, on this dataset.
- The detector is not relying on the label to surface those rings; it surfaces them from timestamp + amount + topology features that exist in the transaction stream alone.

**It does not imply:**
- That graph-native detection would achieve 80% on real bank data. AMLSim's synthetic patterns are deliberately structured to be discoverable; real laundering is messier.
- That the detector is "80% accurate" in a precision/recall sense — the comparison is restricted to *rings the detector flagged*. The detector's recall against the full label-known set (i.e., what fraction of all labeled-1 transactions belong to a detected ring) is a different number and is reported separately in [`docs/calibration.md`](calibration.md).
- That AMLSim's labels are a gold standard. The labels are themselves synthetic, and AMLSim's documentation acknowledges they cover a subset of typologies (fan-in/fan-out, cycles, gather-scatter). A detector that catches a different typology entirely (e.g., dormant-then-active accounts) would score 0% against these labels and could still be correct in production.

## Honest caveats

- **Severity thresholds are demo-grade.** `HIGH` / `MEDIUM` / `CRITICAL` cutoffs were picked to produce a watchable severity distribution on this dataset. A real deployment would tune them against a precision-at-K budget.
- **Control mapping is author-asserted.** `control_bsa`, `control_fatf`, `control_eu_amld` per finding type is a mapping I wrote, not one sourced from a regulator-maintained matrix. The point is to show the *shape* of regulator-facing tagging, not to claim regulatory coverage.
- **Three typologies is not "all of AML."** Smurfing (sub-threshold structuring), pass-through accounts, dormant-then-active, layering through derivatives — none of these are detected here. The roadmap acknowledges this; the typology-agnostic finding schema is the part that's meant to scale.
- **Synthesized 1:1 party-per-account.** Under the post-July-2025 Kaggle AMLSim layout, `HI-Small_accounts.csv` and `HI-Small_Trans.csv` are disjoint at the account-key level. To keep the UI showing per-account ownership, `silver.party` emits a synthetic 1:1 party for any transaction account that has no `accounts_raw` row. These rows are tagged `record_source = 'SYNTHESIZED (1:1 party-per-account)'`. The detector counts and ring topology are unchanged by this synthesis — it's UI-layer only.

## How to verify these claims

Run the pipeline, then:

```bash
# Strict label overlap
docker compose exec -T postgres psql -U kgfc -d kgfincrime -c "
WITH ring_edges AS (
  SELECT fe.finding_id, fe.entity_id AS edge_id
  FROM gold.finding_entity fe
  JOIN gold.finding f ON f.finding_id = fe.finding_id
  WHERE f.finding_type = 'CIRCULAR_FLOW'
    AND fe.entity_type = 'Account'
)
SELECT COUNT(DISTINCT finding_id) FROM ring_edges;
"

# Run the invariants suite
pytest tests/ -v
```

The strict / loose numbers above were measured on the pre-restructure dataset (legacy 3-file Kaggle layout). The current 2-file layout produces the same 109 rings (detector logic is unchanged); the label-overlap measurement re-runs cleanly against the same `bronze.transactions_raw.is_laundering` column.
