"""
services/coverage/sufficiency_rules.py — Operational Sufficiency Rules
(Phase 4 / Wave 3, Hierarchical Knowledge Assurance redesign).

Each rule is a pure, deterministic Python function: (KnowledgeObject) ->
bool. Registered in SUFFICIENCY_RULES by id so a KTTLProfileV2 can
reference a rule by name, and so a Finding can record exactly which
rule (and version) fired -- never "Claude's opinion that this seems
complete."

Wave 3 scope: two real pilot rules (Known Issue, Task), matching the
pilot ontology's attribute set from Wave 2. Not a production-complete
rule library -- one rule per pilot type is enough to prove the
mechanism end-to-end, per the same "small pilot, not full enterprise
ontology" principle Wave 2 used.
"""

from dataclasses import dataclass
from typing import Callable

from schemas.knowledge_element_state import KnowledgeElementState
from schemas.knowledge_graph import KnowledgeObject

RULE_VERSION = 1


def _present(obj: KnowledgeObject, attr_name: str) -> bool:
    attr = obj.attributes.get(attr_name)
    return attr is not None and attr.state == KnowledgeElementState.PRESENT


def known_issue_min_viable_v1(obj: KnowledgeObject) -> tuple[bool, str]:
    """A Known Issue is operationally sufficient only if a receiver can
    tell (a) how it's detected and (b) what to do about it -- either a
    resolution path or an explicit escalation condition (both may be
    N/A-excused independently; this rule only requires at least one
    concrete next step to exist)."""
    has_detection = _present(obj, "detection_method")
    has_next_step = _present(obj, "resolution_path") or _present(obj, "escalation_condition")
    if has_detection and has_next_step:
        return True, ""
    missing = []
    if not has_detection:
        missing.append("detection_method")
    if not has_next_step:
        missing.append("resolution_path or escalation_condition")
    return False, f"missing: {', '.join(missing)}"


def task_min_viable_v1(obj: KnowledgeObject) -> tuple[bool, str]:
    """A Task is operationally sufficient only if a receiver can
    execute it independently: knows when to act, what steps to follow,
    who's responsible, and how to confirm it worked."""
    required = ["trigger_condition", "execution_steps", "responsible_role", "validation_criteria"]
    missing = [attr for attr in required if not _present(obj, attr)]
    return (not missing), (f"missing: {', '.join(missing)}" if missing else "")


@dataclass
class SufficiencyRule:
    rule_id: str
    version: int
    evaluate: Callable[[KnowledgeObject], tuple[bool, str]]


SUFFICIENCY_RULES: dict[str, SufficiencyRule] = {
    "known_issue_min_viable_v1": SufficiencyRule("known_issue_min_viable_v1", RULE_VERSION, known_issue_min_viable_v1),
    "task_min_viable_v1": SufficiencyRule("task_min_viable_v1", RULE_VERSION, task_min_viable_v1),
}


def get_sufficiency_rule(rule_id: str) -> SufficiencyRule:
    if rule_id not in SUFFICIENCY_RULES:
        raise KeyError(f"No sufficiency rule registered for rule_id={rule_id!r}")
    return SUFFICIENCY_RULES[rule_id]
