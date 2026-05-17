"""Refuse pushes that lower Formula/cctally.rb's URL-pinned SemVer.

Server-side counterpart to `cctally release` Phase 6's client-side gate
(cctally-dev issue #30 / commit `27f9428c`). Tracking issue for this
server-side check: cctally-dev #54.

Pure functions (no I/O) drive the comparison; ``main()`` resolves
HEAD / HEAD^ formula text and the HEAD commit message via ``git`` and
prints the result. Unit tests in ``test_check_formula_monotonic.py``
exercise the pure layer; the workflow exercises ``main()``.

Exit codes:
  0 — no downgrade, OR equal versions, OR unparseable URLs, OR override
      trailer present (with warning), OR no previous commit (bootstrap)
  1 — strict downgrade, no override trailer
  2 — internal error (e.g. git invocation failed unexpectedly)
"""
from __future__ import annotations

import argparse
import re
import subprocess
import sys
from dataclasses import dataclass

FORMULA_PATH = "Formula/cctally.rb"
TRAILER_KEY = "Allow-Formula-Downgrade"
TRAILER_VALUE = "true"

_SEMVER_NUM = r"(?:0|[1-9]\d*)"

# Mirrors `_FORMULA_VERSION_RE` in cctally-dev `bin/_cctally_release.py`.
_FORMULA_VERSION_RE = re.compile(
    rf"/v({_SEMVER_NUM}\.{_SEMVER_NUM}\.{_SEMVER_NUM}"
    rf"(?:-[a-zA-Z][a-zA-Z0-9-]*\.{_SEMVER_NUM})?)\.tar\.gz"
)

# Mirrors `_SEMVER_RE` in cctally-dev `bin/_lib_semver.py`.
_SEMVER_RE = re.compile(
    rf"^({_SEMVER_NUM})\.({_SEMVER_NUM})\.({_SEMVER_NUM})"
    rf"(?:-([a-zA-Z][a-zA-Z0-9-]*)\.({_SEMVER_NUM}))?$"
)


def extract_url_version(text: str) -> str | None:
    """Return the SemVer from a `url ".../vX.Y.Z[.tar.gz]"` line, or None."""
    m = _FORMULA_VERSION_RE.search(text)
    return m.group(1) if m else None


def parse_semver(s: str) -> tuple[int, int, int, str | None, int | None]:
    """Parse SemVer; raises ValueError on malformed input."""
    m = _SEMVER_RE.match(s)
    if not m:
        raise ValueError(f"invalid semver: {s!r}")
    major, minor, patch, pre_id, pre_n = m.groups()
    return (
        int(major),
        int(minor),
        int(patch),
        pre_id,
        int(pre_n) if pre_n is not None else None,
    )


def semver_sort_key(
    parsed: tuple[int, int, int, str | None, int | None],
) -> tuple:
    """SemVer §11.4 total-order key. Stable sorts after its prereleases."""
    maj, min_, pat, pre_id, pre_n = parsed
    if pre_id is None:
        return (maj, min_, pat, 1, "", 0)
    return (maj, min_, pat, 0, pre_id, pre_n)


def has_allow_downgrade_trailer(commit_msg: str) -> bool:
    """True iff the commit message contains a literal ``Key: true`` trailer.

    Matched per-line, case-sensitive on key (git trailer convention), with
    optional surrounding whitespace on the value. Anything other than
    exactly ``true`` (e.g. ``yes``, ``1``, ``True``) is rejected so that
    typos don't silently bypass the gate.
    """
    pattern = re.compile(
        rf"^{re.escape(TRAILER_KEY)}:\s*{re.escape(TRAILER_VALUE)}\s*$"
    )
    return any(pattern.match(line) for line in commit_msg.splitlines())


@dataclass(frozen=True)
class Result:
    exit_code: int
    message: str  # rendered to stderr; "" when there's nothing to say


def compute_result(
    prev_text: str | None,
    head_text: str | None,
    commit_msg: str,
) -> Result:
    """Decide whether the HEAD commit constitutes a refused downgrade.

    Returns a `Result` so the caller can route the message to stderr and
    use the exit code as the process exit. Pure (no I/O); the workflow
    glue lives in `main()`.
    """
    # Bootstrap: no previous commit, or formula absent there.
    if prev_text is None:
        return Result(0, "no previous Formula/cctally.rb to compare; passing.")

    # Deletion at HEAD: nothing to validate.
    if head_text is None:
        return Result(0, "Formula/cctally.rb absent at HEAD; nothing to validate.")

    prev_v = extract_url_version(prev_text)
    head_v = extract_url_version(head_text)

    if prev_v is None or head_v is None:
        return Result(
            0,
            "unparseable url= SemVer at HEAD or HEAD^; passing "
            "(bootstrap / schema change tolerated).",
        )

    try:
        prev_key = semver_sort_key(parse_semver(prev_v))
        head_key = semver_sort_key(parse_semver(head_v))
    except ValueError as exc:
        return Result(0, f"SemVer parse failed ({exc}); passing.")

    if head_key >= prev_key:
        return Result(
            0,
            f"OK: v{prev_v} -> v{head_v} (non-decreasing).",
        )

    if has_allow_downgrade_trailer(commit_msg):
        return Result(
            0,
            f"WARNING: formula at HEAD pins v{head_v}, previous commit was "
            f"v{prev_v} (strict downgrade).\n"
            f"`{TRAILER_KEY}: {TRAILER_VALUE}` trailer is present — passing. "
            "Intentional yank / revert?",
        )

    return Result(
        1,
        f"refuse: formula at HEAD pins v{head_v}, previous commit was "
        f"v{prev_v} (strict downgrade).\n"
        "This server-side gate (cctally-dev #54) mirrors the client-side "
        "gate in `cctally release` Phase 6 (cctally-dev #30).\n"
        f"To intentionally land a downgrade (yank / revert), append the "
        f"trailer `{TRAILER_KEY}: {TRAILER_VALUE}` to the commit message.",
    )


def _git_show(ref: str, path: str) -> str | None:
    """Return the blob text at ``<ref>:<path>``, or None if absent."""
    proc = subprocess.run(
        ["git", "show", f"{ref}:{path}"],
        capture_output=True,
        text=True,
        check=False,
    )
    if proc.returncode != 0:
        return None
    return proc.stdout


def _git_log_message(ref: str) -> str:
    """Return the full commit message for ``ref``. Empty on failure."""
    proc = subprocess.run(
        ["git", "log", "-1", "--format=%B", ref],
        capture_output=True,
        text=True,
        check=False,
    )
    if proc.returncode != 0:
        return ""
    return proc.stdout


def _git_rev_parse(ref: str) -> str | None:
    """Return the resolved SHA for ``ref``, or None when unresolvable."""
    proc = subprocess.run(
        ["git", "rev-parse", "--verify", "--quiet", ref],
        capture_output=True,
        text=True,
        check=False,
    )
    if proc.returncode != 0:
        return None
    return proc.stdout.strip() or None


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--head-ref", default="HEAD",
        help="git ref for the commit under inspection (default: HEAD).",
    )
    parser.add_argument(
        "--prev-ref", default="HEAD^",
        help="git ref for the previous commit (default: HEAD^).",
    )
    args = parser.parse_args(argv)

    if _git_rev_parse(args.prev_ref) is None:
        # First commit on the branch: nothing to compare against.
        print(
            f"check_formula_monotonic: {args.prev_ref} does not resolve; "
            "passing (first commit / shallow clone).",
            file=sys.stderr,
        )
        return 0

    prev_text = _git_show(args.prev_ref, FORMULA_PATH)
    head_text = _git_show(args.head_ref, FORMULA_PATH)
    commit_msg = _git_log_message(args.head_ref)

    result = compute_result(prev_text, head_text, commit_msg)
    if result.message:
        print(f"check_formula_monotonic: {result.message}", file=sys.stderr)
    return result.exit_code


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
