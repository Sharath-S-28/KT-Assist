"""
config/templates.py — Scenario generation templates for KT Assist.

Pure Python literals. No I/O, no env reads.

These 110 lines of template strings were the main motivation for
splitting config.py: they don't belong in the same module as DB paths
and API keys. Templates change on scenario-design reviews; settings
change on deployments. Keeping them separate makes both easier to
find and reason about.

One scenario template per knowledge object type (SCENARIO_OBJECT_TEMPLATES)
and one per relationship type (SCENARIO_RELATIONSHIP_TEMPLATES).
Placeholders filled via str.format(name=...) or
str.format(source_name=..., target_name=...) by services/scenario_generation.py.
"""

from config.domain import KNOWLEDGE_OBJECT_TYPES, RELATIONSHIP_TYPES
from config.scoring import CATEGORY_WEIGHTING

# ── Object-type scenario templates ────────────────────────────────────────────

SCENARIO_OBJECT_TEMPLATES = {
    "Process": {
        "category": "Understanding",
        "situation": 'A team member must explain how the "{name}" process works end-to-end.',
        "context": "{name} is a core process within this knowledge transition package.",
        "trigger": "A new team member asks how {name} runs from start to finish.",
        "decision_point": "What are the steps of {name}, performed in what order, and by whom?",
        "evidence": [
            "Describes the steps of {name} in the correct order.",
            "Identifies who is responsible for each step of {name}.",
        ],
    },
    "Task": {
        "category": "Operational",
        "situation": 'A team member is asked to perform the "{name}" task as part of their normal responsibilities.',
        "context": "{name} is a task that must be carried out accurately and on schedule.",
        "trigger": "{name} comes due during a normal operating cycle.",
        "decision_point": "How is {name} performed correctly, and what does 'done' look like?",
        "evidence": [
            "Performs or describes {name} correctly.",
            "States the expected outcome of completing {name}.",
        ],
    },
    "System": {
        "category": "Operational",
        "situation": 'A team member needs to use the "{name}" system to complete their work.',
        "context": "{name} is a system relied on for this process.",
        "trigger": "A task requires interacting with {name}.",
        "decision_point": "How and why is {name} used here, and what is its role?",
        "evidence": [
            "Identifies {name} as the correct system to use.",
            "Explains the role {name} plays in this process.",
        ],
    },
    "Dependency": {
        "category": "Understanding",
        "situation": "A team member must understand what this process depends on beyond its own steps.",
        "context": "{name} is a dependency this process relies on.",
        "trigger": "Someone asks what would happen if {name} were unavailable.",
        "decision_point": "What does this rely on {name} for, and what happens if it fails or is delayed?",
        "evidence": [
            "Identifies {name} as a dependency of this process.",
            "Explains the impact if {name} is delayed or fails.",
        ],
    },
    "Business Rule": {
        "category": "Understanding",
        "situation": 'A team member must apply the "{name}" rule correctly while doing their work.',
        "context": "{name} is a business rule, policy, or threshold governing this process.",
        "trigger": "A situation arises where {name} must be applied or checked.",
        "decision_point": "What does {name} require, and when does it apply?",
        "evidence": [
            "States the requirement of {name} accurately.",
            "Recognizes when {name} applies.",
        ],
    },
    "Risk": {
        "category": "Exception",
        "situation": 'A situation arises where the risk of "{name}" could materialize.',
        "context": "{name} is a known risk associated with this process.",
        "trigger": "Early warning signs of {name} appear during normal operations.",
        "decision_point": "What should be done when {name} starts to materialize?",
        "evidence": [
            "Recognizes the early signs of {name}.",
            "Describes the appropriate mitigating action for {name}.",
        ],
    },
    "Control": {
        "category": "Operational",
        "situation": 'A team member must apply the "{name}" control as part of their routine work.',
        "context": "{name} is a control intended to prevent or detect errors.",
        "trigger": "A scenario occurs where {name} should be exercised.",
        "decision_point": "When and how should {name} be applied?",
        "evidence": [
            "Applies {name} at the correct point in the process.",
            "Explains what {name} is intended to catch.",
        ],
    },
    "Escalation": {
        "category": "Exception",
        "situation": 'An issue arises that may require escalating via "{name}".',
        "context": "{name} defines who to contact and how when an issue arises.",
        "trigger": "A problem occurs that the team member cannot resolve alone.",
        "decision_point": "Who should be contacted via {name}, and through what channel?",
        "evidence": [
            "Identifies the correct contact/channel defined by {name}.",
            "Recognizes when escalation via {name} is warranted.",
        ],
    },
    "Known Issue": {
        "category": "Exception",
        "situation": 'The recurring issue "{name}" reappears during normal operations.',
        "context": "{name} is a known, recurring issue affecting this process.",
        "trigger": "Symptoms matching {name} are observed.",
        "decision_point": "How is {name} recognized and handled when it recurs?",
        "evidence": [
            "Recognizes the symptoms of {name}.",
            "Describes the correct handling/workaround for {name}.",
        ],
    },
}

assert set(SCENARIO_OBJECT_TEMPLATES) == set(KNOWLEDGE_OBJECT_TYPES)
assert {t["category"] for t in SCENARIO_OBJECT_TEMPLATES.values()} <= set(CATEGORY_WEIGHTING)

# ── Relationship scenario templates ───────────────────────────────────────────

SCENARIO_RELATIONSHIP_TEMPLATES = {
    "HAS_TASK": {
        "category": "Understanding",
        "situation": 'A team member must explain how the task "{target_name}" fits within the process "{source_name}".',
        "context": "{target_name} is one of the tasks that make up {source_name}.",
        "trigger": "Someone new to {source_name} asks where {target_name} fits in.",
        "decision_point": "Where does {target_name} fit in the sequence of {source_name}, and why does it matter?",
        "evidence": [
            "Places {target_name} correctly within {source_name}.",
            "Explains why {target_name} matters to {source_name}.",
        ],
    },
    "USES_SYSTEM": {
        "category": "Operational",
        "situation": 'While performing "{source_name}", a team member must use "{target_name}".',
        "context": "{target_name} is the system used to carry out {source_name}.",
        "trigger": "{target_name} becomes slow or briefly unavailable during {source_name}.",
        "decision_point": "Why is {target_name} used for {source_name}, and what is the fallback if it's unavailable?",
        "evidence": [
            "Identifies {target_name} as the system used for {source_name}.",
            "Describes a fallback if {target_name} is unavailable during {source_name}.",
        ],
    },
    "DEPENDS_ON": {
        "category": "Exception",
        "situation": 'While performing "{source_name}", the dependency "{target_name}" becomes unavailable or delayed.',
        "context": "{source_name} depends on {target_name} to complete normally.",
        "trigger": "{target_name} is delayed or fails during {source_name}.",
        "decision_point": "What do you do when {target_name} is unavailable while performing {source_name}?",
        "evidence": [
            "Recognizes that {source_name} depends on {target_name}.",
            "Describes the correct response when {target_name} fails or is delayed.",
        ],
    },
    "GOVERNED_BY": {
        "category": "Understanding",
        "situation": 'While performing "{source_name}", a team member must apply the rule "{target_name}".',
        "context": "{target_name} governs how {source_name} must be carried out.",
        "trigger": "A step in {source_name} triggers the need to apply {target_name}.",
        "decision_point": "How does {target_name} govern the way {source_name} is performed?",
        "evidence": [
            "Applies {target_name} correctly while performing {source_name}.",
            "Explains why {target_name} governs {source_name}.",
        ],
    },
    "HAS_RISK": {
        "category": "Exception",
        "situation": 'While performing "{source_name}", the risk "{target_name}" begins to materialize.',
        "context": "{target_name} is a risk associated with {source_name}.",
        "trigger": "Early warning signs of {target_name} appear during {source_name}.",
        "decision_point": "What should be done when {target_name} starts to materialize during {source_name}?",
        "evidence": [
            "Connects {target_name} to {source_name} correctly.",
            "Describes the right mitigating action for {target_name} during {source_name}.",
        ],
    },
    "MITIGATED_BY": {
        "category": "Operational",
        "situation": 'The risk "{source_name}" is present, and the control "{target_name}" must be applied to mitigate it.',
        "context": "{target_name} is the control intended to reduce {source_name}.",
        "trigger": "A situation arises where {source_name} could materialize.",
        "decision_point": "How does {target_name} mitigate {source_name}, and when should it be applied?",
        "evidence": [
            "Applies {target_name} to mitigate {source_name}.",
            "Explains how {target_name} reduces {source_name}.",
        ],
    },
    "ESCALATES_TO": {
        "category": "Exception",
        "situation": 'An issue arises during "{source_name}" that requires escalating via "{target_name}".',
        "context": "{target_name} defines how issues in {source_name} get escalated.",
        "trigger": "A problem occurs during {source_name} that cannot be resolved alone.",
        "decision_point": "When performing {source_name}, when and how should {target_name} be used?",
        "evidence": [
            "Recognizes when {target_name} is needed during {source_name}.",
            "Identifies the correct contact/channel defined by {target_name}.",
        ],
    },
    "HAS_KNOWN_ISSUE": {
        "category": "Exception",
        "situation": 'While performing "{source_name}", the known issue "{target_name}" recurs.',
        "context": "{target_name} is a known, recurring issue affecting {source_name}.",
        "trigger": "Symptoms matching {target_name} are observed during {source_name}.",
        "decision_point": "How is {target_name} recognized and handled while performing {source_name}?",
        "evidence": [
            "Recognizes {target_name} recurring during {source_name}.",
            "Describes the correct handling of {target_name}.",
        ],
    },
}

assert set(SCENARIO_RELATIONSHIP_TEMPLATES) == set(RELATIONSHIP_TYPES)
assert {t["category"] for t in SCENARIO_RELATIONSHIP_TEMPLATES.values()} <= set(CATEGORY_WEIGHTING)
