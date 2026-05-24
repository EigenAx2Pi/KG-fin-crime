# Calibration

Real numbers measured against the `bronze.is_laundering` ground truth, for each detector. The numbers below were produced by `make demo` on 2026-05-24, on the post-July-2025 AMLSim layout.

These supersede any approximate figures cited elsewhere in the project. The queries that produce them are in this file so anyone can rerun and verify.

## Base rates

| Population | Count |
|---|---:|
| `bronze.transactions_raw` total | 5,078,345 |
| `bronze.transactions_raw` where `is_laundering = 1` | 5,178 (**0.102 %**) |

AMLSim's HI-Small set is extreme-imbalance: 1 in ~1,000 transactions is labeled. This shape is what makes a precision-oriented detector (a few high-quality alerts) more useful than a recall-oriented one (many low-quality alerts) for this dataset and for AML in general.

## Detector precision (edge-level)

For each detector, of the transactions it included in its findings, what fraction are labeled `is_laundering = 1` in the ground truth?

| Detector | Flagged txns | Labeled txns | Precision |
|---|---:|---:|---:|
| `circular_flow` (graph-native, unsupervised) | 130 | 75 | **57.7 %** |
| `mule_hub` (graph-native, unsupervised) | 381 | 96 | **25.2 %** |
| `laundering_exposure` (supervised, control) | 301 | 301 | **100.0 %** *(by construction)* |

`laundering_exposure` is **100 % by definition** — it explicitly reads `bronze.is_laundering = 1` as its candidate filter. It serves as the supervised baseline, not as an unbiased comparison.

`circular_flow` at **57.7 % precision** is the headline graph-native number. Against a base rate of 0.102 %, that's roughly **566× the random precision** of picking transactions blind. `mule_hub` at 25.2 % is ~247× the base rate.

## Detector recall (edge-level)

Of the 5,178 ground-truth labeled transactions in HI-Small, how many are captured by each detector's finding edges?

| Detector | Labeled captured | of 5,178 | Recall |
|---|---:|---:|---:|
| `circular_flow` | 75 | 5,178 | **1.45 %** |
| `mule_hub` | 96 | 5,178 | **1.85 %** |
| **Any graph-native (deduped)** | 171 | 5,178 | **3.30 %** |
| `laundering_exposure` | 301 | 5,178 | 5.81 % *(by construction)* |

Recall is intentionally low. A real AML team's alert capacity is in the hundreds per day, not thousands. The graph-native detectors are tuned to be high-precision-low-recall: surface the structural smoking guns; let downstream surveillance handle the long tail.

This is the right tradeoff for a portfolio piece in AML. It's *not* the right tradeoff for, say, fraud-detection on point-of-sale data where you want every signal you can get and reviewer-cost is low. The point is: **the same finding schema would accommodate a low-precision-high-recall typology** — see `docs/methodology.md` on adding new detectors without forking the schema.

## Ring-level label overlap (the headline number)

For each of `circular_flow`'s 109 detected 3-hop rings, count how many of the ring's hops are labeled in ground truth:

| Measure | Count | of 109 | Pct |
|---|---:|---:|---:|
| **Strict — every hop in the ring is labeled** | 86 | 109 | **78.9 %** |
| **Loose — at least one hop in the ring is labeled** | 91 | 109 | **83.5 %** |
| Total ring hops | 332 | — | — |
| Labeled ring hops | 273 | 332 | 82.2 % |

`circular_flow` does not read `is_laundering` at any point in its SQL — the discipline boundary is enforced by `tests/test_invariants.py::test_graph_native_detector_does_not_read_label`. So **the 78.9 % strict overlap means that pure graph structure recovers ~4 out of 5 rings whose labels would have flagged them anyway**, without ever consulting the label.

This is the core unsupervised-vs-supervised result. See [methodology.md](methodology.md) for why this matters and what it does and does not imply.

## Mule-hub account-level signal

`mule_hub` flags accounts, not transactions. Of the 389 accounts it flagged:

| Slice | Accounts | Pct |
|---|---:|---:|
| Touch ≥1 labeled transaction | 161 | **41.4 %** |
| Touch ≥5 labeled transactions | 35 | 9.0 % |
| Average per-account labeled-transaction ratio | — | **7.0 %** |

Base rate across all transactions is 0.102 %. A flagged account's transactions are labeled at **~68× the base rate** on average. Again, the detector never reads the label — `mule_hub` selects on fan-in/fan-out asymmetry alone.

## How to reproduce

```sql
-- Ring-level label overlap
WITH ring_hops AS (
  SELECT fed.finding_id, t.is_laundering
  FROM silver.finding_edge fed
  JOIN silver.finding sf ON sf.finding_id = fed.finding_id
                         AND sf.assessment_id LIKE 'circular_flow%'
  JOIN silver.transfers_to tt ON tt.fin_txn_id = fed.fin_txn_id
  JOIN bronze.transactions_raw t
       ON t.event_timestamp = tt.event_timestamp
      AND (t.from_bank||':'||t.from_account) = tt.from_account_key
      AND (t.to_bank||':'||t.to_account) = tt.to_account_key
),
per_finding AS (
  SELECT finding_id, COUNT(*) AS edge_count, SUM(is_laundering)::INT AS labeled_edges
  FROM ring_hops GROUP BY finding_id
)
SELECT
  COUNT(*) AS total_rings,
  COUNT(*) FILTER (WHERE labeled_edges = edge_count) AS strict_all_labeled,
  COUNT(*) FILTER (WHERE labeled_edges >= 1) AS loose_any_labeled
FROM per_finding;

-- Per-detector precision
WITH flagged AS (
  SELECT DISTINCT fed.fin_txn_id, sf.assessment_id
  FROM silver.finding_edge fed
  JOIN silver.finding sf ON sf.finding_id = fed.finding_id
)
SELECT
  CASE
    WHEN assessment_id LIKE 'circular_flow%' THEN 'circular_flow'
    WHEN assessment_id LIKE 'mule_hub%' THEN 'mule_hub'
    ELSE 'laundering_exposure'
  END AS detector,
  COUNT(*) AS flagged_txns,
  COUNT(*) FILTER (WHERE bt.is_laundering=1) AS labeled,
  ROUND(100.0 * COUNT(*) FILTER (WHERE bt.is_laundering=1) / COUNT(*), 1) AS precision_pct
FROM flagged f
JOIN silver.financial_transaction ft ON ft.fin_txn_id = f.fin_txn_id
JOIN bronze.transactions_raw bt
  ON bt.event_timestamp = ft.event_timestamp
 AND bt.amount_paid = ft.amount_paid
 AND bt.payment_currency = ft.payment_currency
GROUP BY 1 ORDER BY 1;
```

## Caveats

- **AMLSim is synthetic.** The labels are themselves generated; a detector that scores well against AMLSim does not automatically score well on real bank data, and vice-versa.
- **HI-Small is small.** 5M txns is enough to demonstrate structure but not to study rare typologies that need 10⁸+ rows.
- **Severity thresholds were tuned for demo visibility**, not for any production-grade precision-at-K target.
- **`laundering_exposure` is the supervised control, not a competitive baseline.** Its 100 % precision tells you nothing about graph structure — it tells you that reading the answer key produces a perfect score.
