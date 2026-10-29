# GitCode MCP capability matrix

Matrix revision **1**, evidence checked **2026-10-29 UTC**. Related: [#156](https://github.com/codeasier/gitcode-cli/issues/156).

This is a versioned workflow comparison, not a claim of 89 implemented GitCode tools. It maps the **frozen 89-name GitHub connector appendix in issue 156**, not the current GitHub connector, the entire upstream GitHub MCP server, or the CLI compatibility registry. Names below identify engineering capabilities; they are not copied connector instructions or authorization to execute operations.

## Evidence and delivery boundaries

| Evidence | Pinned observation | What it does not establish |
| --- | --- | --- |
| **S**: MCP source | Source SHA [`70697d26b25abb0cd855cff3350c734fc5586de6`](https://github.com/codeasier/gitcode-cli/commit/70697d26b25abb0cd855cff3350c734fc5586de6); static `SPECS` inspection gives **31 tools: 19 read / 12 write**. Package metadata is `codeasier-gitcode-mcp` **0.3.0**, pinning `pygitcode==0.1.7`. | Source and package-version strings do not prove a published artifact, deployment or successful invocation. |
| **D**: published CLI dependency | [GitHub release v0.1.7](https://github.com/codeasier/gitcode-cli/releases/tag/v0.1.7) exists. The pinned [artifact manifest][published-manifest] identifies wheel/sdist hashes and CLI source SHA **`2f110178d754299214dcdbd94ce41788eb2044ab`**. MCP delegates to services from this installed dependency, not sibling `src/`. | `pygitcode` publishes CLI/services, not MCP tools. Later CLI features on main are not implicitly in this dependency or exposed through MCP. This document does not re-run artifact acceptance. |
| **M**: published MCP | **Unknown/unverified**. The inspected GitHub release list had no `mcp-v*` release; the PyPI lookup was inconclusive. | Absence of a GitHub release is not proof of absence on another registry. No delivered MCP version is asserted. |
| **C**: observed connection | Tool-name discovery on this date exposed **28 tools: 19 read / 9 write**, matching S except W02–W04. Those three names were absent. | Discovery is not execution. Deployed source SHA, package version, token type/scopes, server policy and successful read/write acceptance are **unknown**. No live mutation was performed for this matrix. |
| **F**: comparison baseline | Issue appendix read back with `updated_at=2026-10-28T16:11:11Z`; **89 unique names**. SHA-256 of the names in appendix order, UTF-8, one name per LF-terminated line: `5e7e78995e2bb2e8a5f493b512ffb75a2b7ed4b24169de38d7ea11bc31c14e01`. | A later connector catalog must not silently enlarge this baseline. The issue's original 28/31 observations are historical, separate from C. |

Immutable source references: [registry and dispatch][source-tools], [transport and pagination][source-api], [connection scopes][source-server], [file-write policy][source-file-writes], [package metadata][source-package]. Delegated endpoint evidence uses the pinned dependency's [IssueService][dependency-issues], [PullRequestService][dependency-pulls] and [FileService][dependency-files].

### Status vocabulary

- **Supported**: S exposes the scoped workflow operation, with the documented differences below. This is source support, not release or live certification, and not parameter-for-parameter GitHub parity.
- **Partial**: an exposed operation covers only part of the workflow; the missing semantics are stated.
- **Not implemented**: a source/service or documented endpoint is identified, but no MCP wrapper exists in S. Runtime auth/permission acceptance can still be unknown.
- **API pending**: no equivalent contract has been established here, or key platform semantics remain unverified. This does not assert that GitCode lacks the API.
- **Not applicable**: the named GitHub-specific model has no direct GitCode mapping; adjacent user workflows can still require implementation.

Every comparison row inherits endpoint/auth/permission/pagination, S/D/M/C evidence and delivery status from its referenced catalog or gap profile. Multiple references mean multiple calls, not one atomic operation. For partial mappings, C only declares the existing subset; the missing capability is absent.

## Source tool catalog

All tool names have the `gitcode_` prefix. `R` in an endpoint means `/repos/{owner}/{repo}`. These routes use the fixed base `https://api.gitcode.com/api/v5`; parameters are validated/encoded, not arbitrary URLs.

**Auth/permission profiles:** **R** uses upstream Bearer authentication. OAuth mode uses the current connection's authorization and requires `gitcode:read`; static mode uses the host's configured GitCode token. Both enforce the repository allowlist and upstream access. **W** additionally requires server write mode, OAuth `gitcode:write` when applicable, and upstream permission for the specific operation (including branch/merge restrictions). Exact account-level upstream roles/scopes and successful PAT/OAuth acceptance remain **unknown** for this snapshot; MCP scopes do not grant GitCode privileges. No OAuth-to-shared-PAT fallback is allowed.

**Pagination/limits:** **U** is one upstream page (`page>=1`, default `per_page=30`, maximum 100), with conservative `next_page`; a full last page can be followed by an empty page. **C** is client slicing of one bounded, unpaged upstream response, refetched on each call, not snapshot pagination. **N** means no paging interface, not unlimited content. Every response is bounded (default 2,000,000 bytes); oversized reads fail rather than proving completeness. File-write messages are limited to 4,096 UTF-8 bytes. See [tool contracts](tools.md) and [code publishing](code-publishing.md) for uncertain-write readback and sequential publishing.

**Delivery for every catalog row:** S = present at the SHA above / MCP source 0.3.0; D = installed `pygitcode==0.1.7` where services are delegated; M = unknown. C = **declared, invocation unknown**, except W02–W04 = **absent**. A source tool remains source-supported even when absent from C.

| ID | Tool (without prefix) | Method / v5 endpoint | Auth / permission | Page | Semantic boundary |
| --- | --- | --- | --- | --- | --- |
| R01 | `get_repository` | `GET R` | R | N | Repository metadata; permission fields are upstream observations, not a per-user authorization oracle. |
| R02 | `get_clone_info` | `GET R` | R | N | Derives credential-free clone URLs from repository metadata; does not clone or configure Git credentials. |
| R03 | `list_branches` | `GET R/branches` | R | U | One page; no server-side branch-name search wrapper. |
| R04 | `get_branch` | `GET R/branches/{branch}` | R | N | Literal ref is encoded as one segment; read before relying on a branch head. |
| R05 | `get_file_contents` | `GET R/contents/{path}` | R | N | Explicit ref supported; upstream encoding preserved, not a blob-by-SHA API. |
| R06 | `get_repository_tree` | `GET R/git/trees/{sha}` | R | U | Supports recursive/file_path; missing upstream truncation metadata stays unknown. |
| R07 | `list_commits` | `GET R/commits` | R | U | Ref/path filters; not GitHub commit-search grammar. |
| R08 | `get_commit` | `GET R/commits/{sha}` | R | N | Returns the upstream commit object; no promised GitHub diff schema. |
| R09 | `list_issues` | `GET R/issues` | R | U | Repository-scoped text/state/label filters; assignee filter uses an ID. |
| R10 | `get_issue` | `GET R/issues/{number}` | R | N | Repository issue number, not a global Issue ID. |
| R11 | `list_issue_comments` | `GET R/issues/{number}/comments` | R | U | One page, not an eager all-page fetch. |
| R12 | `list_labels` | `GET R/labels` | R | C | Bounded collection refetched for every local page. |
| R13 | `list_milestones` | `GET R/milestones` | R | C | Bounded collection refetched for every local page. |
| R14 | `list_pull_requests` | `GET R/pulls` | R | U | Repository-scoped filters; GitCode reviewer roles are not issue assignees. |
| R15 | `get_pull_request` | `GET R/pulls/{number}` | R | N | Native merge/review fields; not a complete GitHub review or CI state machine. |
| R16 | `list_pull_request_files` | `GET R/pulls/{number}/files` | R | C | Local slices of one bounded response; pages are not a stable snapshot. |
| R17 | `get_pull_request_diff` | `GET R/pulls/{number}/files.json` | R | N | Native structured diff and diff_refs, not a guaranteed unified patch; use local Git for omitted/oversized content. |
| R18 | `list_pull_request_comments` | `GET R/pulls/{number}/comments` | R | U | One page of native comments; no normalized review-thread graph. |
| R19 | `list_pull_request_commits` | `GET R/pulls/{number}/commits` | R | U | One page; pin and recheck PR head for a multi-call review. |
| W01 | `create_branch` | `POST R/branches` | W | N | New branch from an existing ref; no ref-update/force/lease tool. |
| W02 | `create_file` | `POST R/contents/{path}` | W | N | One commit on an explicit existing branch; decoded content at most 256 KiB. |
| W03 | `update_file` | `PUT R/contents/{path}` | W | N | Whole-file replacement with current Blob SHA; no branch-head compare-and-swap guarantee. |
| W04 | `delete_file` | `DELETE R/contents/{path}` | W | N | Current Blob SHA required; one commit, no multi-file rollback. |
| W05 | `create_issue` | `POST /repos/{owner}/issues` | W | N | Repository supplied in body; assignee is a username; labels/milestone already exposed. |
| W06 | `update_issue` | `PATCH /repos/{owner}/issues/{number}` | W | N | Repository in body; title required; state actions close/reopen. Labels/assignee/milestone exist, but incremental and clear semantics are not promised. |
| W07 | `add_issue_comment` | `POST R/issues/{number}/comments` | W | N | Create a general comment; editing is a separate missing MCP capability. |
| W08 | `create_pull_request` | `POST R/pulls` | W | N | Remote source branch required; draft, labels, milestone and linked-issue arguments exist. Fork source must also pass allowlist. Exposes create arguments named assignees/testers via generic POST; role fulfillment is unverified and dedicated G15 endpoints are not used. |
| W09 | `update_pull_request` | `PATCH R/pulls/{number}` | W | N | Title/body/state/draft/labels/milestone only; no base change or post-create reviewer management. Uses open/closed state values; live acceptance unknown. |
| W10 | `add_pull_request_comment` | `POST R/pulls/{number}/comments` | W | N | General body only; no path/position or discussion-reply schema. |
| W11 | `approve_pull_request` | `POST R/pulls/{number}/review` | W | N | Native approval with force=false; no REQUEST_CHANGES, dismissal or review text in this tool. |
| W12 | `merge_pull_request` | `PUT R/pulls/{number}/merge` | W | N | merge/rebase plus separate squash boolean; no force, atomic expected-head guarantee or protection bypass. |

## Gap profiles: endpoint evidence is not MCP availability

All profiles below are **absent as dedicated MCP capabilities** at S and C. MCP delivery version is **unknown/not delivered by this matrix**. Unless stated otherwise, auth, exact upstream permissions and pagination are **unknown**; existing R/W policies are design constraints, not proof that a new route is authorized. Documented `access_token` parameters are upstream API evidence, not an instruction to put credentials into tool arguments. The current MCP transport only permits repository paths under v5; identity/discovery/search and v8 require deliberate routing and policy work.

| ID | Candidate endpoint / evidence | Auth and permission evidence | Pagination / unresolved difference |
| --- | --- | --- | --- |
| G01 | `GET /api/v5/user`; [CLI UserService at S][cli-users] | CLI wrapper exists; MCP token acceptance and identity disclosure policy unknown. | N for a single profile. No MCP identity tool; login/profile are not inferred from repository ownership. |
| G02 | `GET /api/v5/user/repos`, `/users/{owner}/repos`, `/orgs/{org}/repos`; [CLI RepoService at S][cli-repos] | Existing CLI discovery is not MCP allowlist-safe discovery; OAuth and role coverage unknown. | Service forwards pagination parameters; MCP discovery contract and cross-page coverage unknown. Affiliation/installations filters are not equivalent. |
| G03 | [`GET /api/v5/search/repositories`][api-search-repos] | Official docs list an authorization-code parameter; Bearer/OAuth acceptance, scopes and result allowlist enforcement unknown. | Docs: page max 100, per_page max 20. GitHub search syntax and streaming semantics are not promised. |
| G04 | [`GET /api/v5/search/issues`][api-search-issues]; `GET /api/v5/user/issues` also exists in [dependency IssueService][dependency-issues] | MCP wrapper absent; OAuth/access filtering unknown. | Search docs: page max 100, per_page max 50; user-issue MCP pagination unknown. R09 only searches one known repository. |
| G05 | `PATCH /api/v5/repos/{owner}/{repo}/issues/comments/{id}`; [dependency IssueService][dependency-issues] | Comment ownership/edit permission and live OAuth acceptance unknown. | N; comment ID differs from issue number. Service exists, MCP edit wrapper absent. |
| G06 | `POST /api/v5/repos/{owner}/{repo}/pulls/{number}/discussions/{discussion_id}/comments`; [dependency PullRequestService][dependency-pulls] | Reply/ownership rules and OAuth acceptance unknown. | N; requires a native discussion ID, not a GitHub GraphQL thread node. W10 only posts a general comment. |
| G07 | [`PUT /api/v5/repos/{owner}/{repo}/pulls/{number}/comments/{discussion_id}`][api-discussion-state] | Docs list authorization-code input; resolve/reopen permissions and OAuth acceptance unknown. | N; body `resolved` selects state. No normalized thread model or MCP wrapper. |
| G08 | [`PATCH /api/v5/repos/{owner}/{repo}/pulls/comments/{id}`][api-edit-pr-comment] | Ownership/edit permission and OAuth acceptance unknown. | N; no MCP edit wrapper, and GitHub review-comment IDs are not interchangeable. |
| G09 | [`GET /api/v8/repos/{owner}/{repo}/actions/runs`][api-runs] | Docs list authorization-code input; CI permissions and Bearer/OAuth acceptance unknown. | page default 1, per_page default 20/max 100. Match returned head_sha to the requested commit; PR/branch filtering alone is insufficient. |
| G10 | [`GET /api/v8/repos/{owner}/{repo}/actions/runs/{run_id}/jobs`][api-jobs] and [job detail][api-job] | CI permissions and Bearer/OAuth acceptance unknown. | Jobs docs do not specify paging parameters; bounded completeness strategy pending. Native job/step IDs need a contract. |
| G11 | [`POST /api/v8/repos/{owner}/{repo}/actions/runs/{run_id}/jobs/{job_id}/logs`][api-logs] | Semantically a **read** despite POST; auth and CI permissions unknown. | step_id plus offset/limit/sort; response has has_more/start_offset/end_offset. No MCP v8/log wrapper. |
| G12 | [`POST /api/v8/repos/{owner}/{repo}/actions/runs/{run_id}/retry`][api-retry]; [run-level rerun][api-rerun] | Authorized CI mutation required; exact permissions and OAuth acceptance unknown. | N; retry takes job_run_ids, rerun targets the whole run. Equivalence to GitHub single-job retry and partial-success behavior pending. |
| G13 | Endpoint **unknown** for the requested equivalent operation | Authentication, permissions and live acceptance **unknown**. | Pagination/size contract **unknown**. Used for atomic Git Data writes, blob/compare/search gaps, reactions/locking, review dismissal/records, auto-merge, collaborator/org lookup, status aggregation and artifact/download behavior until independently established. |
| G14 | GitHub App installation/account selector has no direct mapping in this matrix | Not applicable to the GitHub-specific model; GitCode identity/discovery auth remains G01/G02. | Not applicable to that selector, not a claim that repository discovery is complete. |
| G15 | At S, [CLI role services][cli-pulls] and [role/readback contract][cli-people] implement `POST/DELETE R/pulls/{number}/assignees` and `POST/DELETE R/pulls/{number}/reviewers` (v5). | Native assignees (审查人) and approval reviewers (评审人, response field `approval_reviewers`) are distinct; assignment is not approval. MCP OAuth/role/live acceptance remains unknown. These newer CLI methods are not in pinned D 0.1.7 and are not MCP wrappers. | N. Assignee POST uses JSON, DELETE uses query `assignees`; reviewer POST uses JSON `reviewers` with `add:true`, DELETE uses JSON `reviewers`. CLI verifies membership/identities and preserves unrelated people; operations are non-atomic. |
| G16 | At S, [CLI PR services][cli-pulls] expose `POST R/pulls/{number}/labels` (JSON array) and `DELETE R/pulls/{number}/labels/{name}`; [CLI IssueService][cli-issues] exposes `DELETE R/issues/{number}/labels/{name}` (v5). | MCP-specific incremental wrappers are absent; upstream account roles and OAuth/live acceptance unknown. These dedicated methods are newer than pinned D 0.1.7. | N. Dedicated add/remove is not the generic labels field exposed by W06/W09; empty/clear and concurrent replacement behavior must not be assumed. |
| G17 | [Dependency PullRequestService][dependency-pulls] exposes `GET R/pulls/{number}/diff`; [CLI service at S][cli-pulls] also exposes `GET R/pulls/{number}/patch` with mail-patch validation (v5). | Native raw-read routes exist in services; MCP OAuth/live acceptance unknown. The newer patch wrapper is not in pinned D 0.1.7. | N; MCP R17 still calls `files.json`, not these raw routes. Complete diff/patch size/omission and revision handling need an MCP contract. |

## Frozen GitHub baseline: one row per name

The following 89 rows preserve F's order. A catalog reference uses S plus its pinned delegated-service evidence; a gap reference records only its stated candidate/unknown contract. The comparison is deliberately conservative about replacement, clearing, role differences and revision consistency.

| GitHub baseline tool | Source status | Mapping / evidence profile | Difference or remaining work |
| --- | --- | --- | --- |
| `add_comment_to_issue` | Supported | W07, W10 | Use the Issue or PR general-comment operation appropriate to the target. |
| `add_issue_assignees` | Partial | W06 | Single assignee field exists; plural incremental add semantics are not established. |
| `add_issue_labels` | Partial | W06, R10 | Labels exist; additive merge/concurrency semantics are not guaranteed. |
| `add_reaction_to_issue_comment` | API pending | G13 | Reaction creation contract not established. |
| `add_reaction_to_pr` | API pending | G13 | Reaction creation contract not established. |
| `add_reaction_to_pr_review_comment` | API pending | G13 | Native comment identity and reaction creation contract pending. |
| `add_review_to_pr` | Partial | W11, W10 | Native approval plus separate text; no REQUEST_CHANGES or batched line review. |
| `compare_commits` | API pending | G13 | No MCP compare wrapper; base/head diff, pagination and revision contract pending. |
| `convert_pull_request_to_draft` | Supported | W09 | Set draft=true; upstream acceptance and permissions remain unverified. |
| `create_blob` | API pending | G13 | Single-file publishing is not a standalone Git blob write. |
| `create_branch` | Supported | W01 | Create from an existing ref; no update-ref lease semantics. |
| `create_commit` | API pending | G13 | File writes create individual commits; no arbitrary tree/parent commit constructor. |
| `create_file` | Supported | W02 | One explicit remote branch/file; absent from observed connection C. |
| `create_issue` | Supported | W05 | Native assignee, labels and milestone supported; preserve ID/username distinctions. |
| `create_pull_request` | Partial | W08 | Core lifecycle exists; fork_path/reviewer roles differ from GitHub. |
| `create_tree` | API pending | G13 | Tree reading does not implement a Git tree write or atomic multi-file commit. |
| `delete_file` | Supported | W04 | Current file Blob SHA required; absent from C. |
| `dismiss_pull_request_review` | API pending | G13 | GitCode review/test/reset roles need separate verification; approval is not dismissal. |
| `download_user_content` | API pending | G13 | No constrained attachment-download contract; arbitrary URL fetching is not exposed. |
| `download_workflow_artifact` | API pending | G13 | Download source, redirect/auth boundary and size limit pending. |
| `enable_auto_merge` | API pending | G13 | Immediate merge is not scheduled or conditional auto-merge. |
| `fetch` | Partial | R01–R19, G13 | Dedicated repository reads only; no general URL/API reader. |
| `fetch_blob` | Partial | R05, G13 | File-at-ref reading exists; arbitrary blob-SHA lookup is not exposed. |
| `fetch_commit` | Partial | R08 | Native commit detail; GitHub diff/metadata equivalence not assumed. |
| `fetch_commit_workflow_runs` | Not implemented | G09 | Runs endpoint identified; exact commit association and v8 policy needed. |
| `fetch_file` | Supported | R05 | Preserves upstream encoding; caller must choose and retain the intended ref. |
| `fetch_issue` | Supported | R10 | Repository-scoped issue number. |
| `fetch_issue_comments` | Partial | R11 | One page per call, not an all-pages aggregate. |
| `fetch_pr` | Supported | R15 | Native PR fields rather than a GitHub-normalized object. |
| `fetch_pr_comments` | Partial | R18 | One native page; comment/review categories may differ. |
| `fetch_pr_file_patch` | Partial | R16, R17 | Select native file/diff data; no dedicated guaranteed file patch contract. |
| `fetch_pr_patch` | Partial | R17, G17 | MCP returns structured diff; service raw diff/patch routes exist but are not MCP wrappers. |
| `fetch_workflow_job_logs` | Not implemented | G11 | Step-scoped paginated read route identified; no MCP wrapper. |
| `fetch_workflow_job_steps` | Not implemented | G10 | Job/step payload exists in docs; native identity mapping pending. |
| `fetch_workflow_run_artifacts` | API pending | G13 | Artifact list contract and limits not established here. |
| `fetch_workflow_run_jobs` | Not implemented | G10 | Documented jobs route; bounded collection handling pending. |
| `get_commit_combined_status` | API pending | G09, G13 | Runs alone do not equal combined required-check/commit status. |
| `get_issue_comment_reactions` | API pending | G13 | Reaction-read contract not established. |
| `get_pr_diff` | Partial | R17 | Structured diff with native refs; truncation/omission needs explicit handling. |
| `get_pr_info` | Partial | R15 | Core PR metadata, not full review/CI merge-readiness aggregation. |
| `get_pr_reactions` | API pending | G13 | Native reaction-read contract not established here. |
| `get_pr_review_comment_reactions` | API pending | G13 | Comment-ID mapping and reaction contract pending. |
| `get_profile` | Not implemented | G01 | CLI identity service exists but is not an MCP tool. |
| `get_repo` | Supported | R01 | Repository metadata and current access observation. |
| `get_repo_collaborator_permission` | Partial | R01, G13 | Current repository permission fields are not an arbitrary collaborator lookup. |
| `get_user_login` | Not implemented | G01 | No MCP current-user/login tool. |
| `get_users_recent_prs_in_repo` | Partial | R14 | Repository filters exist; account-specific recency/author equivalence needs verification. |
| `label_pr` | Partial | W09, R15, G16 | MCP labels field exists; dedicated incremental CLI routes are not exposed by MCP. |
| `list_installations` | Not applicable | G14 | GitHub App installation model; GitCode discovery remains separate work. |
| `list_installed_accounts` | Not applicable | G14 | GitHub installed-account selector; do not infer GitCode identity/org coverage. |
| `list_pr_changed_filenames` | Partial | R16 | Client-paged native files, not an atomic all-page filename snapshot. |
| `list_pull_request_review_threads` | Partial | R18, G13 | Native comments only; normalized thread/state/position traversal absent. |
| `list_pull_request_reviews` | Partial | R15, G13 | Current native review indicators are not a historical review-record list. |
| `list_recent_issues` | Partial | R09, G04 | Known-repository list only; cross-repository authorized enumeration absent. |
| `list_repositories` | Not implemented | G02 | CLI services exist; MCP discovery and allowlist filtering absent. |
| `list_repositories_by_affiliation` | Not implemented | G02 | Native repository lists need verified affiliation mapping. |
| `list_repositories_by_installation` | Not applicable | G14, G02 | Installation selector is GitHub-specific; user/org repository discovery absent. |
| `list_user_org_memberships` | API pending | G13 | Organization membership roles and pagination not established. |
| `list_user_orgs` | API pending | G13 | No MCP organization-list contract; org repository list is not membership enumeration. |
| `lock_issue_conversation` | API pending | G13 | Locking/reason/permission contract not established. |
| `mark_pull_request_ready_for_review` | Supported | W09 | Set draft=false; not a review approval or merge-readiness guarantee. |
| `merge_pull_request` | Partial | W12, R15 | Native checks; no GitHub method enum parity or atomic expected-head promise. |
| `remove_issue_assignees` | Partial | W06 | Assignee field exists; safe clear/plural removal semantics unverified. |
| `remove_issue_label` | Partial | W06, R10, G16 | Generic labels field exists; dedicated CLI removal route has no MCP wrapper. |
| `remove_pull_request_reviewers` | Not implemented | G15 | Dedicated CLI role/removal contracts exist; MCP wrappers and OAuth/live acceptance absent. |
| `remove_reaction_from_issue_comment` | API pending | G13 | Removal contract and native reaction identifiers pending. |
| `remove_reaction_from_pr` | API pending | G13 | Removal contract pending. |
| `remove_reaction_from_pr_review_comment` | API pending | G13 | Native comment/reaction ID mapping pending. |
| `reply_to_review_comment` | Not implemented | G06 | Service route exists; native discussion IDs required, no MCP reply wrapper. |
| `request_pull_request_reviewers` | Partial | W08, G15 | Create parameters named assignees/testers exist, but role fulfillment is unverified; dedicated post-create role services lack MCP wrappers. |
| `rerun_failed_workflow_run_jobs` | Not implemented | G12 | Native retry candidate; selection and failure semantics need acceptance. |
| `rerun_workflow_job` | API pending | G12 | job_run_ids retry is not assumed equivalent to rerunning any GitHub job. |
| `resolve_review_thread` | Not implemented | G07 | Native resolved=true route; no MCP wrapper or GraphQL ID translation. |
| `search` | API pending | G13 | No general code-search MCP contract or assumed GitHub query grammar. |
| `search_branches` | Partial | R03 | Caller may inspect pages; no server-side branch-search wrapper. |
| `search_commits` | Partial | R07, G13 | Ref/path list is not full commit search. |
| `search_installed_repositories_streaming` | Not implemented | G03, G14 | Native search candidate; installation/streaming model not reproduced. |
| `search_installed_repositories_v2` | Not implemented | G03, G14 | Native search candidate; installation selector not applicable. |
| `search_issues` | Partial | R09, G04 | Repository keyword filter exists; independent/cross-repository search absent. |
| `search_prs` | Partial | R14, G13 | Repository list filters only, not full GitHub search syntax. |
| `search_repositories` | Not implemented | G03 | Official endpoint identified; MCP wrapper and OAuth/allowlist acceptance absent. |
| `unlock_issue_conversation` | API pending | G13 | Unlock/permission contract not established. |
| `unresolve_review_thread` | Not implemented | G07 | Native resolved=false route; no MCP wrapper. |
| `update_file` | Supported | W03 | Whole file and current Blob SHA; absent from C; no branch-head CAS guarantee. |
| `update_issue` | Partial | W06 | Title required, close/reopen actions; labels/assignee/milestone already exist, clear semantics pending. |
| `update_issue_comment` | Not implemented | G05 | Dependency service exists; MCP edit wrapper absent. |
| `update_pull_request` | Partial | W09 | Draft/labels/milestone exist; no base change or role update; clear semantics not assumed. |
| `update_ref` | API pending | G13 | Create branch and sequential file commits do not implement ref update/lease/force. |
| `update_review_comment` | Not implemented | G08 | Native comment-edit route; no MCP wrapper or GitHub review-ID equivalence. |

## Updating and verifying this matrix

1. Retain the frozen baseline names/order/digest. A scope change needs a separately identified baseline, not a silent recount of a live connector.
2. Read the actual `SPECS` AST and dispatch at the proposed source SHA without importing the runtime. Compare exact tool-name sets, read/write flags, argument models, endpoint methods and pinned dependency services. Update S/D separately if either changes.
3. Validate all 89 comparison names exactly once, all 31 source names exactly once in the catalog, referenced profile IDs and Markdown links. Documentation-only/static checking does not establish API acceptance; use the existing CI for the final PR revision.
4. For a release claim, record the independently published MCP version, immutable source/artifact identity and acceptance evidence. The `pygitcode` release or a successful source-compatibility job cannot supply that claim. Follow the [release guide](releases.md).
5. For a connection claim, rediscover schemas in the intended connection and record the deployment identity and approved sandbox results separately: a read; OAuth/read-only/write-scope behavior; allowlist denial; pagination/limits; and only explicitly authorized writes with remote readback. A new tool name alone is insufficient.
6. Before promoting a gap, verify its endpoint/auth/roles, version routing, pagination/size limits, IDs and error/uncertain-outcome behavior. For CI, preserve exact commit/run/job/step association. For file publishing, retain sequential writes and verify remote state; never infer atomicity, rollback or lease from read-before-write.

This revision changes documentation only. It does not register new tools, alter migration candidates, deploy OAuth, publish packages, weaken identity or permission gates, or certify completion of the broader roadmap.

[source-tools]: https://github.com/codeasier/gitcode-cli/blob/70697d26b25abb0cd855cff3350c734fc5586de6/packages/gitcode-mcp/src/gitcode_mcp/tools.py
[source-api]: https://github.com/codeasier/gitcode-cli/blob/70697d26b25abb0cd855cff3350c734fc5586de6/packages/gitcode-mcp/src/gitcode_mcp/api.py
[source-server]: https://github.com/codeasier/gitcode-cli/blob/70697d26b25abb0cd855cff3350c734fc5586de6/packages/gitcode-mcp/src/gitcode_mcp/server.py
[source-file-writes]: https://github.com/codeasier/gitcode-cli/blob/70697d26b25abb0cd855cff3350c734fc5586de6/packages/gitcode-mcp/src/gitcode_mcp/file_writes.py
[source-package]: https://github.com/codeasier/gitcode-cli/blob/70697d26b25abb0cd855cff3350c734fc5586de6/packages/gitcode-mcp/pyproject.toml
[published-manifest]: https://github.com/codeasier/gitcode-cli/blob/70697d26b25abb0cd855cff3350c734fc5586de6/packages/gitcode-mcp/published-cli.json
[dependency-issues]: https://github.com/codeasier/gitcode-cli/blob/2f110178d754299214dcdbd94ce41788eb2044ab/src/gitcode_cli/services/issues.py
[dependency-pulls]: https://github.com/codeasier/gitcode-cli/blob/2f110178d754299214dcdbd94ce41788eb2044ab/src/gitcode_cli/services/pulls.py
[dependency-files]: https://github.com/codeasier/gitcode-cli/blob/2f110178d754299214dcdbd94ce41788eb2044ab/src/gitcode_cli/services/files.py
[cli-users]: https://github.com/codeasier/gitcode-cli/blob/70697d26b25abb0cd855cff3350c734fc5586de6/src/gitcode_cli/services/users.py
[cli-repos]: https://github.com/codeasier/gitcode-cli/blob/70697d26b25abb0cd855cff3350c734fc5586de6/src/gitcode_cli/services/repos.py
[cli-pulls]: https://github.com/codeasier/gitcode-cli/blob/70697d26b25abb0cd855cff3350c734fc5586de6/src/gitcode_cli/services/pulls.py
[cli-issues]: https://github.com/codeasier/gitcode-cli/blob/70697d26b25abb0cd855cff3350c734fc5586de6/src/gitcode_cli/services/issues.py
[cli-people]: https://github.com/codeasier/gitcode-cli/blob/70697d26b25abb0cd855cff3350c734fc5586de6/docs/en/pr-people.md
[api-search-repos]: https://docs.gitcode.com/docs/apis/get-api-v-5-search-repositories/
[api-search-issues]: https://docs.gitcode.com/en/docs/apis/get-api-v-5-search-issues/
[api-discussion-state]: https://docs.gitcode.com/docs/apis/put-api-v-5-repos-owner-repo-pulls-number-comments-discussions-id/
[api-edit-pr-comment]: https://docs.gitcode.com/docs/apis/patch-api-v-5-repos-owner-repo-pulls-comments-id/
[api-runs]: https://docs.gitcode.com/en/docs/apis/get-api-v-8-repos-owner-repo-actions-runs/
[api-jobs]: https://docs.gitcode.com/en/docs/apis/get-api-v-8-repos-owner-repo-actions-runs-run-id-jobs/
[api-job]: https://docs.gitcode.com/en/docs/apis/get-api-v-8-repos-owner-repo-actions-runs-run-id-jobs-job-id/
[api-logs]: https://docs.gitcode.com/en/docs/apis/post-api-v-8-repos-owner-repo-actions-runs-run-id-jobs-job-id-logs/
[api-retry]: https://docs.gitcode.com/en/docs/apis/post-api-v-8-repos-owner-repo-actions-runs-run-id-retry/
[api-rerun]: https://docs.gitcode.com/en/docs/apis/post-api-v-8-repos-owner-repo-actions-runs-run-id-rerun/
