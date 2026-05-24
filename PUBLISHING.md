# Publishing nz-akahu-mcp to PyPI

This repo ships a GitHub Actions workflow (`.github/workflows/release.yml`) that
builds, gates, and publishes to PyPI using **Trusted Publishing** (OIDC). No
long-lived API tokens live in repo secrets.

## One-time PyPI setup

You have to do this once, before the first release.

### 1. Register the project name on PyPI

Trusted Publishing on PyPI requires the project to exist before you can configure
the publisher. Two ways to bootstrap:

**Option A (recommended): pending publisher.** PyPI lets you pre-configure a
trusted publisher for a project that does not yet exist. Sign in to
https://pypi.org, go to **Your account -> Publishing -> Add a new pending
publisher**, and fill in:

| Field              | Value                                  |
| ------------------ | -------------------------------------- |
| PyPI Project Name  | `nz-akahu-mcp`                         |
| Owner              | `severity1`                            |
| Repository name    | `nz-akahu-mcp`                         |
| Workflow filename  | `release.yml`                          |
| Environment name   | `pypi`                                 |

The first time the workflow publishes, PyPI creates the project and binds the
trusted publisher to it permanently.

**Option B: manual first upload.** Build locally, upload once with an API token,
then convert to Trusted Publishing afterwards (see "Manual publish" below).

### 2. Create the `pypi` GitHub environment

In the GitHub repo: **Settings -> Environments -> New environment -> `pypi`**.

Optional (recommended) protections to add on the environment:

- **Required reviewers:** add yourself. Every publish then waits for your manual
  approval click in the GitHub Actions UI. Lets you catch a wrong-tag release
  before it hits PyPI.
- **Deployment branches:** restrict to `main` so a release cut from a feature
  branch can't publish.

The environment name MUST exactly match the `environment.name` in the workflow
and the environment name you registered in PyPI's pending publisher.

### 3. (Optional) Repeat for TestPyPI

To dry-run releases against TestPyPI first, register a parallel pending publisher
on https://test.pypi.org and duplicate the publish job in the workflow with
`repository-url: https://test.pypi.org/legacy/`. Useful before the very first
production release.

## Cutting a release

Once the one-time setup is done, every release is three steps:

```bash
# 1. Bump the version in pyproject.toml.
#    The workflow asserts pyproject version == release tag (minus the 'v').
#    Edit `version = "0.1.0"` to the new number.

# 2. Commit and tag.
git commit -am "release: v0.2.0"
git tag v0.2.0
git push origin main v0.2.0
```

```text
# 3. In the GitHub UI: Releases -> Draft a new release.
#    - Tag: v0.2.0 (the one you just pushed)
#    - Title: v0.2.0
#    - Generate release notes (auto-fills from commits since last tag)
#    - Click "Publish release"
```

Publishing the release triggers the workflow:

- `test` job: ruff + mypy + pytest (100% coverage gate)
- `build` job: `uv build` -> sdist + wheel, version-vs-tag check
- `publish` job: pauses on the `pypi` environment for your approval (if you
  configured required reviewers), then OIDC-publishes to PyPI

The package appears at https://pypi.org/project/nz-akahu-mcp/ within a minute,
and `uvx nz-akahu-mcp` / `pip install nz-akahu-mcp` start resolving it.

## Manual publish (fallback)

If the GitHub flow is broken or you need a hotfix from your laptop:

```bash
# 1. Clean build:
rm -rf dist/
uv build

# 2. Publish via uv (uses ~/.pypirc or UV_PUBLISH_TOKEN env var):
uv publish

# or via twine:
uvx twine upload dist/*
```

For the manual path you do need an API token: create one at
https://pypi.org/manage/account/token/ scoped to this project, then either put
it in `~/.pypirc` or export `UV_PUBLISH_TOKEN=pypi-...`. After your first
successful upload via token, configure the trusted publisher (above) and stop
using the token.

## Version policy

This project follows semver. Until 1.0:

- `0.x.y` -> `0.x.(y+1)` for bug fixes and additive changes
- `0.x.y` -> `0.(x+1).0` for breaking changes (tool removals, tool signature
  changes, environment-variable renames, safety-default flips)

Document every breaking change in the GitHub release notes.

## Yanking a bad release

If a published release is broken:

```bash
uvx twine yank nz-akahu-mcp --version 0.2.0 --reason "Broken refresh handling, use 0.2.1"
```

Yanking hides the version from new installs but doesn't remove it (so users with
it pinned still resolve). Follow up immediately with a patched release.
