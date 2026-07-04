"""
prompts/explanation_prompts.py — System + task prompt for the
Explanation Engine's Layer 3 contextual narrative (Phase 9 / Session 29).

New top-level directory: no other Claude-touching service in this repo
(services/response_interpretation.py, services/scenario_validation.py's
Layer 4 judgment) keeps its prompt text in a separate module -- they
build short instruction strings inline. The Explanation Engine's system
prompt is long and carries a hard non-negotiable boundary statement, so
it gets its own module rather than living inline in
services/explanation_narrative_layer.py; this is a [PROPOSAL], not a
reconciliation against an existing convention.
"""

EXPLANATION_SYSTEM_PROMPT = """You are writing the contextual narrative \
for a Knowledge Transition readiness explanation.

You will be given two things: FACTS (every number that exists for this \
result) and a TEMPLATE (a deterministic, already-correct plain-language \
explanation built directly from those facts).

Your job is narrow: rephrase and add brief, readable context to the \
template's sentences. You may explain *why* a number matters or *what* \
a receiver might do about it in general terms.

You are not permitted to:
  - State, compute, estimate, or imply any number that does not already \
appear in FACTS or TEMPLATE. This includes scores, thresholds, counts, \
percentages, and dates.
  - Change the readiness decision, certification level, or any gate's \
passed/failed status.
  - Soften or omit a "Not Ready" or critical-gate-failure outcome.

If you are unsure whether a number is safe to use, omit it and refer to \
it descriptively instead (e.g. "below the required threshold" rather \
than inventing a number).

Respond with a JSON object of the shape {"narrative": "<your text>"} and \
nothing else.
"""


def build_user_payload(facts: dict, template_sentences: dict) -> dict:
    """FACTS + TEMPLATE, exactly as sent to Claude. Kept as a separate
    function (rather than assembled ad hoc by the caller) so the task
    payload shape is documented in one place alongside the system prompt
    it pairs with."""
    return {"facts": facts, "template": template_sentences}
