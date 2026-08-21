from __future__ import annotations

from cygnus_decision_engine.policyops import policy_allows_mode


def test_dry_run_is_always_safe() -> None:
    assert policy_allows_mode(None, "DRY_RUN")
    assert policy_allows_mode("DRAFT", "DRY_RUN")
    assert policy_allows_mode("SHADOW", "DRY_RUN")
    assert policy_allows_mode("ACTIVE", "DRY_RUN")


def test_shadow_requires_registered_shadow_or_active_policy() -> None:
    assert not policy_allows_mode(None, "SHADOW")
    assert not policy_allows_mode("DRAFT", "SHADOW")
    assert policy_allows_mode("SHADOW", "SHADOW")
    assert policy_allows_mode("ACTIVE", "SHADOW")
    assert not policy_allows_mode("PAUSED", "SHADOW")
    assert not policy_allows_mode("RETIRED", "SHADOW")


def test_live_requires_explicit_active_policy() -> None:
    assert not policy_allows_mode(None, "LIVE")
    assert not policy_allows_mode("DRAFT", "LIVE")
    assert not policy_allows_mode("SHADOW", "LIVE")
    assert policy_allows_mode("ACTIVE", "LIVE")
    assert not policy_allows_mode("PAUSED", "LIVE")
    assert not policy_allows_mode("RETIRED", "LIVE")


def test_unknown_mode_is_blocked() -> None:
    assert not policy_allows_mode("ACTIVE", "UNKNOWN")
