# GitCode Actions artifacts

```sh
gc run artifacts RUN_ID -R owner/repo --page 1 --limit 20
gc run download RUN_ID -R owner/repo --artifact-id ARTIFACT_ID --attempt 1 --commit HEAD_SHA --output ./artifact.zip
```

- `run artifacts` lists one page for the observed run ID and verifies its workflow, head commit and current attempt before and after listing. The API identifies an artifact's run, not its attempt. After a rerun, `artifact_attempt` is null. The list contains no download links.
- `run download` saves one raw ZIP. It does not choose a run or artifact by name, invent an attempt association, extract entries, or overwrite anything. An explicit artifact ID, full head commit SHA and observed first attempt are required. Downloads from later attempts are not enabled because the API has no per-artifact attempt field. The workflow, run, exact artifact ID, byte size and SHA-256 must agree across the documented list and detail endpoints, and the download must match the size and digest. These are provider metadata checks, not cryptographic provenance attestations.
- The output must be a new `.zip` file in an existing user-owned directory not writable by other users or groups. Download requires POSIX directory-descriptor support, rejects symlink path components and stages the verified ZIP before an atomic no-overwrite install. On incompatible platforms use `run artifacts` for evidence and the provider's UI for downloads.
- The fixed GitCode Actions endpoint returns a signed transfer location. Storage requests and redirects use no reusable GitCode token, cookie or environment proxy, only HTTPS to exact GitCode/AtomGit provider hosts and public network addresses. The provider does not document the possible external storage hosts; unknown destinations fail closed. Transfer is capped at 512 MiB. If the provider uses an unrecognized storage host or does not return a size or digest, retrieve the artifact through the provider UI rather than overriding verification.

Provider contracts: [list artifacts for a run](https://atomgit-api-doc.atomgit.com/en/17.actions/262.list_specific_run_artifacts.html), [artifact details](https://atomgit-api-doc.atomgit.com/17.actions/263.get_artifact_details.html), [artifact ZIP redirect](https://atomgit-api-doc.atomgit.com/en/17.actions/265.download_the_specified_artifact.html).

The client applies a 30-second socket inactivity timeout and checks its 300-second
transfer budget between operations. That budget is not a hard wall-clock bound
during DNS or a blocking header/chunk read. Only a fully verified ZIP is installed.
