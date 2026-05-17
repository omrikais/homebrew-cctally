"""Unit tests for check_formula_monotonic.

Run via `pytest .github/scripts/` from the repo root, or implicitly via
.github/workflows/refuse-formula-downgrade.yml. The pure-function layer
covers the entire decision matrix; main() is exercised end-to-end by
the workflow itself on every push.
"""
from __future__ import annotations

import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).parent))

from check_formula_monotonic import (  # noqa: E402
    compute_result,
    extract_url_version,
    has_allow_downgrade_trailer,
    parse_semver,
    semver_sort_key,
)


def _formula(version: str) -> str:
    """Minimal valid-looking formula text pinning ``version``."""
    return (
        'class Cctally < Formula\n'
        f'  url "https://github.com/omrikais/cctally/archive/refs/tags/v{version}.tar.gz"\n'
        '  sha256 "deadbeef"\n'
        'end\n'
    )


# ---------- extract_url_version ----------

def test_extract_stable():
    assert extract_url_version(_formula("1.7.4")) == "1.7.4"


def test_extract_prerelease():
    assert extract_url_version(_formula("1.8.0-rc.1")) == "1.8.0-rc.1"


def test_extract_missing_returns_none():
    assert extract_url_version('class Cctally < Formula\nend\n') is None


def test_extract_rejects_non_semver_in_url():
    # `v1.7` (no patch) is not a valid SemVer per the regex.
    text = 'url "https://example.com/v1.7.tar.gz"\n'
    assert extract_url_version(text) is None


# ---------- semver_sort_key ordering ----------

def test_patch_upgrade_orders_higher():
    assert semver_sort_key(parse_semver("1.7.4")) > semver_sort_key(parse_semver("1.7.3"))


def test_minor_upgrade_orders_higher():
    assert semver_sort_key(parse_semver("1.8.0")) > semver_sort_key(parse_semver("1.7.4"))


def test_stable_higher_than_prerelease_at_same_mmp():
    # SemVer §11.4: 1.7.4 > 1.7.4-rc.1
    assert semver_sort_key(parse_semver("1.7.4")) > semver_sort_key(parse_semver("1.7.4-rc.1"))


def test_prerelease_below_next_stable():
    # 1.8.0-rc.1 still upgrades from 1.7.4 stable
    assert semver_sort_key(parse_semver("1.8.0-rc.1")) > semver_sort_key(parse_semver("1.7.4"))


def test_prerelease_counter_orders():
    assert semver_sort_key(parse_semver("1.8.0-rc.2")) > semver_sort_key(parse_semver("1.8.0-rc.1"))


# ---------- has_allow_downgrade_trailer ----------

def test_trailer_exact_match():
    msg = "chore(formula): cctally 1.7.3\n\nReverting bad release.\nAllow-Formula-Downgrade: true\n"
    assert has_allow_downgrade_trailer(msg)


def test_trailer_extra_whitespace_ok():
    msg = "subject\n\nAllow-Formula-Downgrade:   true  \n"
    assert has_allow_downgrade_trailer(msg)


def test_trailer_missing():
    assert not has_allow_downgrade_trailer("chore(formula): cctally 1.7.3\n")


def test_trailer_wrong_value_rejected():
    # Typos must not bypass the gate.
    for bad_value in ("yes", "1", "True", "TRUE", "ok"):
        msg = f"subject\n\nAllow-Formula-Downgrade: {bad_value}\n"
        assert not has_allow_downgrade_trailer(msg), f"{bad_value!r} should not pass"


def test_trailer_wrong_key_case_rejected():
    msg = "subject\n\nallow-formula-downgrade: true\n"
    assert not has_allow_downgrade_trailer(msg)


def test_trailer_inside_body_text_rejected():
    # Must be a whole-line trailer, not embedded in prose.
    msg = "see Allow-Formula-Downgrade: true note above\n"
    assert not has_allow_downgrade_trailer(msg)


# ---------- compute_result ----------

def test_strict_downgrade_refused():
    r = compute_result(_formula("1.7.4"), _formula("1.7.3"), "chore(formula): cctally 1.7.3\n")
    assert r.exit_code == 1
    assert "v1.7.4" in r.message and "v1.7.3" in r.message
    assert "refuse" in r.message


def test_strict_downgrade_allowed_with_trailer():
    msg = "chore(formula): cctally 1.7.3\n\nAllow-Formula-Downgrade: true\n"
    r = compute_result(_formula("1.7.4"), _formula("1.7.3"), msg)
    assert r.exit_code == 0
    assert "WARNING" in r.message


def test_patch_upgrade_passes():
    r = compute_result(_formula("1.7.3"), _formula("1.7.4"), "chore(formula): cctally 1.7.4\n")
    assert r.exit_code == 0


def test_equal_version_passes():
    r = compute_result(_formula("1.7.4"), _formula("1.7.4"), "re-push\n")
    assert r.exit_code == 0


def test_minor_upgrade_passes():
    r = compute_result(_formula("1.7.4"), _formula("1.8.0"), "chore(formula): cctally 1.8.0\n")
    assert r.exit_code == 0


def test_prerelease_under_stable_at_same_mmp_is_downgrade():
    # 1.7.4 -> 1.7.4-rc.1 is a §11.4 downgrade.
    r = compute_result(_formula("1.7.4"), _formula("1.7.4-rc.1"), "subject\n")
    assert r.exit_code == 1


def test_prerelease_then_stable_passes():
    r = compute_result(_formula("1.8.0-rc.1"), _formula("1.8.0"), "chore(formula): cctally 1.8.0\n")
    assert r.exit_code == 0


def test_no_previous_bootstrap_passes():
    r = compute_result(None, _formula("1.0.0"), "initial formula\n")
    assert r.exit_code == 0


def test_head_deletion_passes():
    r = compute_result(_formula("1.7.4"), None, "remove formula\n")
    assert r.exit_code == 0


def test_unparseable_head_passes():
    head = 'class Cctally < Formula\n  # url omitted\nend\n'
    r = compute_result(_formula("1.7.4"), head, "schema change\n")
    assert r.exit_code == 0


def test_unparseable_prev_passes():
    prev = 'class Cctally < Formula\nend\n'
    r = compute_result(prev, _formula("1.7.4"), "first url\n")
    assert r.exit_code == 0
