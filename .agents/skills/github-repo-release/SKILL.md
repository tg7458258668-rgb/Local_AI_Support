---
name: github-repo-release
description: Standardize and publish this repository to GitHub as a versioned release. Use when the user asks to organize the GitHub repository, make the version easy to see, clean upload candidates, document the release process, bump VERSION/FastAPI metadata, commit, tag, push, or repeat the guarded upload workflow for Local AI Support.
---

# Github Repo Release

## Overview

Use this skill to keep the Local AI Support GitHub repository tidy and release-ready. It combines repository presentation, version discipline, upload safety checks, and normal GitHub push/tag verification.

## Release Workflow

1. Confirm the repository root with `pwd`, `git rev-parse --show-toplevel`, `git status --short --branch`, and `git remote -v`.
2. Choose the next semantic version:
   - Patch (`x.y.z+1`) for docs, cleanup, dependency metadata, or release process changes.
   - Minor (`x.y+1.0`) for user-facing features or workflow additions.
   - Major only for breaking behavior.
3. Update every visible version location:
   - `VERSION`
   - `support_app/main.py` FastAPI `version=`
   - top of `README.md`
   - newest entry in `CHANGELOG.md`
4. Keep GitHub presentation clear:
   - README starts with current version, release status, quick links, and run commands.
   - `CHANGELOG.md` lists newest release first.
   - `docs/RELEASE_WORKFLOW.md` explains the repeatable upload process.
5. Protect upload candidates:
   - Verify `.gitignore` excludes `.venv/`, `.env`, `.env.*`, `runtime/`, `*.log`, `*.pid`, `*.bak`, `__pycache__/`, `.DS_Store`, `data/qdrant_storage/`, `data/doc_page_images/`, and temporary inspection output.
   - Keep `.env.example` trackable.
   - Do not print or commit secrets.
6. Clean generated local files before staging:
   - Remove `.DS_Store`, `__pycache__/`, `.pytest_cache/`, and `*.bak`.
   - Use `git clean -fX <path>` only for ignored generated output that is safe to regenerate.
7. Verify before commit:
   - `python3 -m compileall support_app app scripts`
   - `./.venv/bin/python -m pytest` when `.venv` exists; otherwise use `python3 -m pytest` if available.
   - `node --check app/static/admin.js`
   - `node --check app/static/chat-v2.js`
   - `git ls-files | rg 'qdrant_storage|runtime|\.env$|\.env\.|\.log$|\.pid$|\.bak$|__pycache__|\.DS_Store' || true`
8. Commit and tag:
   - `git add .`
   - Inspect `git diff --cached --stat` and `git diff --cached --name-status`.
   - Commit as `Release vX.Y.Z`.
   - Create tag `vX.Y.Z`.
9. Push normally:
   - `git fetch origin main --tags`
   - `git push origin main`
   - `git push origin vX.Y.Z`
   - Never force-push unless the user explicitly asks to replace remote history.
10. Verify remote:
   - `git ls-remote origin refs/heads/main refs/tags/vX.Y.Z`
   - `git log --oneline -1 --decorate`
   - `git status --short --branch`

## Failure Handling

- If pytest collects scripts unexpectedly, constrain collection with `pytest.ini` instead of deleting useful debug scripts.
- If PyPI SSL verification fails during local setup, prefer a one-time `--trusted-host` install over changing global pip configuration.
- If a tag already exists, inspect it first and do not overwrite a published tag without explicit user approval.
- If the remote rejects a normal push, fetch and inspect divergence before deciding whether to merge, rebase, or ask the user.
