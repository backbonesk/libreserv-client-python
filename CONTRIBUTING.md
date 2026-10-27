# Contributing to libreserv-client

Thanks for your interest. Pull requests and issues are welcome on GitHub.

## How changes land

Development happens in BACKBONE's GitLab, which is the source of truth; the
GitHub repository is a read-only mirror of the `master` branch and its tags.
That has two visible consequences for contributors:

- **Your pull request is merged through GitLab, not with the GitHub merge
  button.** A maintainer imports your branch, reviews it, and squash-merges
  it. When the resulting commit reaches `master`, the mirror pushes it to
  GitHub and your PR is closed automatically with a reference to that
  commit (GitHub shows it as "closed", not "merged" — that is expected).
- **Attribution is preserved.** The squash commit carries a
  `Co-authored-by:` trailer for every author of the original commits, so
  your name and avatar appear on the landed commit.

Each pull request becomes exactly one commit on `master`, so keep PRs
focused on one change.

## Before opening a PR

```sh
uv sync
uv run pytest
uv run ruff check src tests
uv run mypy --strict src          # the package ships py.typed; keep it clean
```

The library supports Python 3.9+ and httpx 0.24+; please keep new code
within that floor (no syntax or stdlib features newer than 3.9 at runtime).
Add a line to `CHANGELOG.md` under the unreleased version for anything
user-visible.

## Reporting bugs

Use GitHub issues. Please do not open public issues for security problems —
see `SECURITY.md`.
