# Independent MCP releases

`pygitcode` and `codeasier-gitcode-mcp` are separate distributions. CLI `v*` tags
continue to use the existing CLI workflow. MCP uses `mcp-vX.Y.Z` tags and
`.github/workflows/publish-mcp.yml`; it never rewrites the checked-in version
from a tag. This workflow prepares publication, **not deployment**.

## Current boundary

- The MCP source version is `0.3.0`, with `pygitcode==0.1.6` still pinned.
- A source changelog entry or successful CI run is not proof of a PyPI release.
- This change does not create a tag, publish a package, configure credentials,
  modify GitHub/PyPI security settings, upgrade a server, or change the downstream
  Codex bridge's immutable dependency. Those are separate authorized actions.
- Shared service compatibility is checked separately against the CLI checkout;
  that does not silently substitute checkout code into the published MCP wheel.

## Before enabling publication (operator action)

These persistent settings are prerequisites, **not created by the workflow**:

1. Confirm the intended PyPI project is `codeasier-gitcode-mcp` and who owns it.
   Configure a PyPI Trusted Publisher for owner `codeasier`, repository
   `gitcode-cli`, workflow filename `publish-mcp.yml`, environment `mcp-pypi`.
   Use the pending-publisher flow if the project does not exist. Do not add a
   fallback API token to the repository.
2. Create and review the GitHub environment `mcp-pypi` before enabling releases.
   Require an authorized reviewer, enable **Prevent self-review**, and configure
   exactly one selected deployment policy: type **tag**, pattern `mcp-v*`. Review tag rules/permissions so only authorized maintainers can
   create release tags. The nonprivileged gate verifies the environment and its
   deployment policy through unauthenticated, read-only public GitHub API calls
   before acceptance and again immediately before scheduling publication. A
   missing environment, missing/weak reviewer rule, broad or unknown policy,
   API refusal, redirect, rate limit or incomplete response fails closed; there
   is no token fallback and no administrative permission request.
3. Only after both settings have been verified, set the **repository-level**
   variable `MCP_PYPI_PUBLISH_ENABLED=true`. This opt-in deliberately lives outside
   the environment and is not itself evidence of protection. Both the opt-in and
   live protection checks must pass before a publish job references the environment.
   Never set the variable as a substitute for configuring the environment or trust mapping.

No such settings have been changed as part of implementing this workflow. An
unset/false opt-in fails tag publication closed. `workflow_dispatch` is always a
validation-only run, even if an existing tag is selected.

## Release review and validation

1. Review the exact candidate commit on `main`. Update both
   `packages/gitcode-mcp/pyproject.toml` and `src/gitcode_mcp/__init__.py` together,
   then add nonempty notes to the package's own `CHANGELOG.md`.
2. Keep dependency changes separate and explicitly reviewed. In particular the
   current `pygitcode==0.1.6` guard is deliberate; changing it requires shared
   service/transport compatibility evidence, not a blind dependency bump.
3. Obtain successful CLI CI and independent MCP CI on the exact candidate.
   The release workflow reuses the full MCP workflow on the tag's commit:
   - Python 3.11, 3.12 and 3.13 lint/tests;
   - source/tag/import version, Python floor, entry-point and dependency checks;
   - wheel and sdist metadata agreement with source, clean independent installs;
   - offline stdio/HTTP checks and synthetic legacy access/refresh-token continuity;
   - nonroot Docker packaging and real synthetic Compose-volume takeover/rollback.
   The immutable legacy source and version remain fixed; the candidate's runtime
   version may advance. No real GitCode request or production state is used.
4. A manual **Publish GitCode MCP** run may rehearse these gates without
   publication. Inspect its exact commit, jobs and distribution artifacts.
5. Only after release approval and prerequisite verification, an authorized
   operator may create a new `mcp-vX.Y.Z` tag for that reviewed commit. Tag version
   must exactly equal source version and the tagged commit must be reachable from
   `main`. Only new tag creation is accepted, not force pushes, updates or deletion.
   The live remote tag (including annotated-tag peeling) must still resolve to
   the event commit at source validation and after acceptance. This guide does not
   itself authorize creating the tag.

The privileged publication job runs only for a matching tag-push event, after all
MCP acceptance jobs succeed and the protected environment permits it. It downloads
the **immutable artifact ID** returned only by the Python 3.12 producer from
**that same run**, not a mutable lookup by artifact name, with no source checkout
or rebuild. Missing/invalid producer outputs stop before download. The manifest
SHA256 also travels through job/workflow outputs independently of artifact storage. Before installation CI records a manifest binding the source commit,
version, exact filenames and SHA256 digests, then rechecks those bytes after the
acceptance tests. Publication independently checks the downloaded manifest against
the source gate and producer manifest digest, and fails closed on extra files,
links or hash differences; the
artifact service's warning-only digest check is not the publication gate. Only the
verified `dist/` files go to PyPI, never the manifest. Only
this job receives `id-token: write`; all test/build jobs use `contents: read`.
Artifacts contain only the two distributions and public integrity manifest; never
OAuth databases, fixture state, environment files or logs.

## Verify and handle failures

After an authorized publication, verify both distributions and their digests on
PyPI, their metadata and clean installation, and record the release commit and CI
run. A package publication is not a production acceptance or a bridge upgrade.
Schedule any production switch separately using the migration/rollback guide.

Publication deliberately does not use `skip-existing`. If upload partially
succeeds or its result is uncertain, inspect PyPI before retrying; do not blindly
rerun, overwrite artifacts, move a published tag, or substitute rebuilt bytes.
If required security setup is missing, stop publication and have an authorized
operator complete it; never work around a failed environment or OIDC gate.


## Security boundary

The required environment reviewer must independently recheck the live tag,
commit, workflow contents, tested artifacts and PyPI trust mapping before
approval. Keep the protected environment and tag rules unchanged while a release
is pending. Read-only preflight is a point-in-time observation, not an atomic lock
against an administrator concurrently deleting or weakening settings.

Workflow checks do not sandbox someone who can modify the workflow itself.
Authorization ultimately rests on independently maintained tag rules, environment
review/protection and the exact PyPI OIDC trust mapping. Do not treat a green
self-check or the opt-in variable as a replacement for those controls. The checks
only read existing settings; they never create, repair or broaden them.

API contracts: [Get an environment](https://docs.github.com/en/rest/deployments/environments#get-an-environment)
and [List deployment branch policies](https://docs.github.com/en/rest/deployments/branch-policies#list-deployment-branch-policies).
