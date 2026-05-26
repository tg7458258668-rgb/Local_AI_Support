# Release Workflow

This document is the repeatable process for uploading this repository to GitHub as a clean, versioned release.

## Version Rule

Use semantic versions stored without the `v` prefix in `VERSION`.

- Patch: documentation, cleanup, metadata, tests, release process changes.
- Minor: new user-facing features, new workflows, or meaningful app behavior additions.
- Major: breaking changes that require migration.

Every release must keep these in sync:

- `VERSION`
- `support_app/main.py` FastAPI `version=`
- `README.md` current version line
- `CHANGELOG.md` newest entry
- Git tag `vX.Y.Z`

## Preflight

```bash
pwd
git rev-parse --show-toplevel
git status --short --branch
git remote -v
git fetch origin main --tags
```

Confirm that `origin` points to:

```text
https://github.com/tg7458258668-rgb/Local_AI_Support.git
```

## Cleanup

Only remove generated local output, never source files or business data:

```bash
find . -name '.DS_Store' -type f -delete
find . -name '__pycache__' -type d -prune -exec rm -rf {} +
find . -name '*.bak' -type f -delete
rm -rf .pytest_cache
git clean -fX data/doc_page_images
```

The following paths should remain ignored and uncommitted:

```text
.venv/
.env
.env.*
runtime/
data/qdrant_storage/
data/doc_page_images/
tmp_docx_inspect/
*.log
*.pid
*.bak
```

## Verification

```bash
python3 -m compileall support_app app scripts
./.venv/bin/python -m pytest
node --check app/static/admin.js
node --check app/static/chat-v2.js
git ls-files | rg 'qdrant_storage|runtime|\.env$|\.env\.|\.log$|\.pid$|\.bak$|__pycache__|\.DS_Store' || true
```

The only expected match from the forbidden-file check is `.env.example`.

## Commit, Tag, Push

```bash
git add .
git diff --cached --stat
git diff --cached --name-status
git commit -m "Release vX.Y.Z"
git tag vX.Y.Z
git push origin main
git push origin vX.Y.Z
```

Use a normal push first. Do not force-push unless the user explicitly asks to replace remote history.

## Remote Verification

```bash
git ls-remote origin refs/heads/main refs/tags/vX.Y.Z
git log --oneline -1 --decorate
git status --short --branch
```

The branch and tag hashes should match the release commit, and the local working tree should be clean.
