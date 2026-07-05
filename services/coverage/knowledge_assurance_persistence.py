"""
services/coverage/knowledge_assurance_persistence.py — KAR Persistence
(Phase 4 / Wave 7, Hierarchical Knowledge Assurance redesign).

Separate from services/coverage/coverage_persistence.py's
persist_coverage_result() on purpose: that function is v1's canonical,
already-fixed-twice writer (see its own docstring's bug history) and
takes a KVAResult, not a KnowledgeAssuranceResult -- forcing the two
shapes through one function would mean branching internal logic on
which kind of result was passed, exactly the kind of "coverage_engine.py
decides one way, something else decides another way" risk Ruling 4
warned against. Same CoverageResult table, two small, single-purpose
writers.

`coverage_score` (the legacy, NOT NULL column) is populated from KCS as
the closest analogous single number for anything that queries this
table generically without knowing it's a v2 row -- but the real,
complete picture for a v2 row is the kcs_score/kqs_score/etc. columns,
never coverage_score alone.
"""

from sqlalchemy.orm import Session

from models.coverage import CoverageResult
from schemas.knowledge_assurance import KnowledgeAssuranceResult


def persist_knowledge_assurance_result(db: Session, kar: KnowledgeAssuranceResult) -> CoverageResult:
    """Persist one KnowledgeAssuranceResult as a CoverageResult row.
    Caller commits (matching persist_coverage_result's own contract --
    see its call sites for the pattern)."""
    coverage_result = CoverageResult(
        package_id=kar.package_id,
        graph_version_id=kar.graph_version_id,
        coverage_score=kar.kcs if kar.kcs is not None else 0.0,
        sufficiency_gate_passed=kar.sufficiency_gate_passed,
        domain_breakdown_json=None,  # v1-specific concept; not meaningful for a v2/dimensional result
        kcs_score=kar.kcs, tc_score=kar.tc, ac_score=kar.ac, rc_score=kar.rc,
        kqs_score=kar.kqs, os_score=kar.os, ev_score=kar.ev,
        quality_gate_applicable=kar.quality_gate_applicable,
        quality_gate_passed=kar.quality_gate_passed,
    )
    db.add(coverage_result)
    db.flush()
    return coverage_result
