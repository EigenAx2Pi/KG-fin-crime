"""Invariants that protect the project's structural claims.

Two layers:
- **Static** (always runs): source-level assertions about the detectors. These
  are the Pillar-1 discipline boundary — graph-native detectors must not read
  the ground-truth label. If someone refactors a detector and accidentally
  joins to `bronze.is_laundering`, this test fails before the change merges.
- **DB-backed** (skips if Postgres is unreachable): shape assertions on the
  produced findings. Run after `make pipeline`.

Run from repo root:
    pytest tests/                  # static only if DB is down, full suite if up
    pytest tests/ -m static        # only the source-level invariants
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
SRC = REPO_ROOT / "src"

GRAPH_NATIVE_DETECTORS = ("circular_flow.py", "mule_hub.py")
KNOWN_FINDING_TYPES = {"CIRCULAR_FLOW", "MULE_HUB", "LAUNDERING_EXPOSURE"}


# ---------- static invariants (no DB needed) --------------------------------


@pytest.mark.static
@pytest.mark.parametrize("filename", GRAPH_NATIVE_DETECTORS)
def test_graph_native_detector_does_not_read_label(filename: str) -> None:
    """A graph-native detector that grew an `is_laundering` dependency would
    silently undo the Pillar-1 discipline boundary. The CI failure here is the
    point: anyone making that change has to either rename their detector or
    justify why the boundary should move.
    """
    source = (SRC / "assessments" / filename).read_text()
    # Permit one explicit acknowledgement comment, otherwise no mention.
    # Strip comments before searching so docstring/header text doesn't trip.
    code = re.sub(r"#.*", "", source)
    code = re.sub(r'"""[\s\S]*?"""', "", code)
    code = re.sub(r"'''[\s\S]*?'''", "", code)
    assert "is_laundering" not in code, (
        f"{filename}: graph-native detector references `is_laundering` in "
        f"executable code. If this is intentional, move the detector out of "
        f"the graph-native category and update README + docs/methodology.md."
    )


@pytest.mark.static
def test_finding_schema_shape_is_typology_agnostic() -> None:
    """Every assessment writes to silver.finding* keyed by assessment_id and
    finding_type. If one detector forks the schema, the gold publisher's
    typology-agnostic claim is no longer true.
    """
    for name in ("circular_flow.py", "mule_hub.py", "laundering_exposure.py"):
        source = (SRC / "assessments" / name).read_text()
        # Must INSERT into silver.finding (the parent table) and reference
        # finding_entity/finding_edge — not custom typology tables.
        assert "INSERT INTO silver.finding" in source, f"{name}: must write to silver.finding"
        assert "silver.finding_entity" in source, f"{name}: must write to silver.finding_entity"


# ---------- DB-backed invariants --------------------------------------------


def _connect_or_skip():
    try:
        from common.db import connect
    except ImportError:
        pytest.skip("kg-fin-crime not installed (run `pip install -e .`)")
    try:
        return connect()
    except Exception as e:  # noqa: BLE001 — covers network, auth, etc.
        pytest.skip(f"Postgres not reachable: {e}")


@pytest.mark.db
def test_every_finding_has_account_entities() -> None:
    """Every finding represents activity over Account nodes — there must be
    at least one Account row per finding in silver.finding_entity. A finding
    without Accounts means the ring/hub/exposure logic dropped its
    constituent nodes.
    """
    conn = _connect_or_skip()
    with conn, conn.cursor() as cur:
        cur.execute("""
            SELECT f.finding_id
            FROM silver.finding f
            LEFT JOIN silver.finding_entity fe
                   ON fe.finding_id = f.finding_id AND fe.entity_type = 'Account'
            GROUP BY f.finding_id
            HAVING COUNT(fe.entity_id) = 0
            LIMIT 5
        """)
        offenders = cur.fetchall()
    assert not offenders, f"Findings with no Account entities: {offenders}"


@pytest.mark.db
def test_finding_types_are_known() -> None:
    conn = _connect_or_skip()
    with conn, conn.cursor() as cur:
        cur.execute("SELECT DISTINCT finding_type FROM silver.finding")
        observed = {row[0] for row in cur.fetchall()}
    unexpected = observed - KNOWN_FINDING_TYPES
    assert not unexpected, (
        f"Unexpected finding_type values in silver.finding: {unexpected}. "
        f"If you added a new detector, register its type in tests/test_invariants.py."
    )


@pytest.mark.db
def test_gold_finding_count_matches_silver() -> None:
    """gold.* is meant to be a faithful projection of silver.finding*. If the
    counts diverge, the publisher dropped or duplicated rows.
    """
    conn = _connect_or_skip()
    with conn, conn.cursor() as cur:
        cur.execute("SELECT COUNT(*) FROM silver.finding")
        (silver_count,) = cur.fetchone()
        cur.execute("SELECT COUNT(*) FROM gold.finding")
        (gold_count,) = cur.fetchone()
    assert silver_count == gold_count, (
        f"silver.finding has {silver_count} rows but gold.finding has {gold_count}. "
        f"Re-run `python -m gold.publish`."
    )
