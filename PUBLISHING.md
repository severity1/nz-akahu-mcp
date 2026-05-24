# Publishing nz-akahu-mcp to PyPI

The GitHub Actions workflow at `.github/workflows/release.yml` builds, gates,
and publishes to PyPI via **Trusted Publishing** (OIDC).

## One-time PyPI setup

Required before the first release.

### 1. Register the project name on PyPI

Trusted Publishing requires the project to exist before configuring the
publisher. Two ways to bootstrap:

**Option A: pending publisher.** Sign in to https://pypi.org, go to
**Your account -> Publishing -> Add a new pending publisher**, and fill in:

| Field              | Value                                  |
| ------------------ | -------------------------------------- |
| PyPI Project Name  | `nz-akahu-mcp`                         |
| Owner              | `severity1`                            |
| Repository name    | `nz-akahu-mcp`                         |
| Workflow filename  | `release.yml`                          |
| Environment name   | `pypi`                                 |

The first publish creates the project and binds the trusted publisher to it
permanently.

**Option B: manual first upload.** Build locally, upload once with an API token,
then convert to Trusted Publishing afterwards (see "Manual publish" below).

### 2. Create the `pypi` GitHub environment

In the GitHub repo: **Settings -> Environments -> New environment -> `pypi`**.

Recommended environment protections:

- **Required reviewers:** add yourself. Every publish waits for manual approval
  in the GitHub Actions UI.
- **Deployment branches:** restrict to `main`.

The environment name must match the `environment.name` in the workflow and the
environment name registered with PyPI's pending publisher.

### 3. (Optional) Repeat for TestPyPI

To dry-run releases against TestPyPI, register a parallel pending publisher on
https://test.pypi.org and duplicate the publish job in the workflow with
`repository-url: https://test.pypi.org/legacy/`.

## Cutting a release

1. **Bump the version** in `pyproject.toml`. The workflow asserts the pyproject
   `version` matches the release tag (minus the leading `v`).

2. **Commit, tag, and push:**

   ```bash
   git commit -am "release: vX.Y.Z"
   git tag vX.Y.Z
   git push origin main vX.Y.Z
   ```

3. **Publish a GitHub Release** with that tag (Releases -> Draft a new release
   -> select the tag -> Generate release notes -> Publish release).

The Release event triggers the workflow:

- `test`: ruff + mypy + pytest (100% coverage gate)
- `build`: `uv build` produces sdist + wheel; asserts pyproject version == tag
- `publish`: pauses on the `pypi` environment for approval (if required
  reviewers are configured), then OIDC-publishes to PyPI

The package appears at https://pypi.org/project/nz-akahu-mcp/ within a minute,
and `uvx nz-akahu-mcp` / `pip install nz-akahu-mcp` start resolving it.

## Manual publish (fallback)

```bash
# 1. Clean build:
rm -rf dist/
uv build

# 2. Publish via uv (uses ~/.pypirc or UV_PUBLISH_TOKEN env var):
uv publish

# or via twine:
uvx twine upload dist/*
```

The manual path requires an API token: create one at
https://pypi.org/manage/account/token/ scoped to this project, then put it in
`~/.pypirc` or export `UV_PUBLISH_TOKEN=pypi-...`. After the first upload,
configure the trusted publisher (above) and stop using the token.

## Version policy

Semver. Until 1.0:

- `0.x.y` -> `0.x.(y+1)` for bug fixes and additive changes
- `0.x.y` -> `0.(x+1).0` for breaking changes (tool removals, tool signature
  changes, environment-variable renames, safety-default flips)

Document every breaking change in the GitHub release notes.

## Yanking a bad release

```bash
uvx twine yank nz-akahu-mcp --version X.Y.Z --reason "Broken refresh handling, use X.Y.(Z+1)"
```

Yanking hides the version from new installs but does not remove it; pinned
installs still resolve. Follow up with a patched release.
