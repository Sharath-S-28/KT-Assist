"""
services/coverage/condition_evaluator.py — shared, deliberately narrow
condition-language evaluator (Phase 4 / Wave 2, Hierarchical Knowledge
Assurance redesign).

Single canonical implementation, used by both validation_plan_builder.py
(ValidationPlan construction) and attribute_arbitration.py (deterministic
NOT_APPLICABLE evaluation during arbitration) -- Wave 2 ruling requires
one condition-language implementation, not two independently-drifting
copies.

Wave 2 ruling: keep this deliberately narrow. Supported grammar is
exactly `attribute == literal` (case-insensitive literal match). No
arbitrary Python evaluation, no expression engine, no boolean DSL, no
dynamic code execution.

Unsupported syntax must fail SAFELY and VISIBLY -- raising
UnsupportedConditionSyntaxError, never silently returning False. A
condition string that doesn't match the supported grammar is a
configuration defect, not a legitimate "the condition is false."
Callers decide how to surface that (Wave 2's builder/arbitration record
it in a visible diagnostics list rather than crashing the whole run).
"""

import re

from schemas.knowledge_graph import KnowledgeObject
from schemas.knowledge_element_state import KnowledgeElementState

_CONDITION_RE = re.compile(r"^\s*(\w+)\s*==\s*'?([\w.]+)'?\s*$")


class UnsupportedConditionSyntaxError(ValueError):
    """Raised when a condition string doesn't match the supported
    `attribute == literal` grammar. Never caught and silently
    swallowed into a False result -- callers must record it visibly."""

    def __init__(self, condition: str):
        self.condition = condition
        super().__init__(f"Unsupported condition syntax: {condition!r}. Only 'attribute == literal' is supported.")


def evaluate_condition(condition: str, obj: KnowledgeObject) -> bool:
    """Evaluate a narrow `attribute == literal` condition against an
    object's PRESENT attributes. An attribute that isn't PRESENT cannot
    confirm the condition, so it evaluates False (a legitimate false,
    not a syntax problem) -- absence of grounds is not the same as
    malformed syntax.

    Raises UnsupportedConditionSyntaxError for anything outside the
    supported grammar.
    """
    match = _CONDITION_RE.match(condition)
    if not match:
        raise UnsupportedConditionSyntaxError(condition)
    attr_name, expected = match.groups()
    attr = obj.attributes.get(attr_name)
    if attr is None or attr.state != KnowledgeElementState.PRESENT:
        return False
    return str(attr.value).lower() == expected.lower()
