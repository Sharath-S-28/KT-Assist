"""
services/role_threshold.py — Role-gated OIS threshold resolution
(Phase 2 / Session 5).

Locked design decision: three-tier receiver role model (Primary /
Secondary / Oversight) with role-gated thresholds. This module resolves
the *first-pass* effective OIS threshold for a role tier by applying
config.ROLE_TIER_THRESHOLD_ADJUSTMENT to the base Operational Readiness
Gate threshold (config.OIS_READINESS_THRESHOLD), then clamps the result
at the override floor (config.OIS_OVERRIDE_FLOOR) so no tier adjustment
can push a receiver's bar below the floor.

This is deliberately the simple, single-lever version of the threshold
model. The full three-lever tier-adjusted model with boundary-zone
precedence is implemented in Phase 8 / Session 27, which will supersede
(not duplicate) this function — kept here as the Session 5 scaffold so
role assignments have a real, usable threshold from day one rather than
a bare string tag.
"""

import config
from utils.errors import ValidationFailedError


def resolve_effective_ois_threshold(role_tier: str) -> int:
    """Return the OIS threshold a receiver in `role_tier` must clear."""
    if role_tier not in config.ROLE_TIER_THRESHOLD_ADJUSTMENT:
        raise ValidationFailedError(
            f"Unrecognized receiver role tier: {role_tier!r}. "
            f"Must be one of {config.RECEIVER_ROLE_TIERS}.",
            details={"role_tier": role_tier},
        )
    adjustment = config.ROLE_TIER_THRESHOLD_ADJUSTMENT[role_tier]
    threshold = config.OIS_READINESS_THRESHOLD + adjustment
    return max(threshold, config.OIS_OVERRIDE_FLOOR)
