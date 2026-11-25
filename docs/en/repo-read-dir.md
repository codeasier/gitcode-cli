# Read a repository directory

List the immediate children of a path without cloning. Omit the path to list the root of a branch, commit or tree SHA. An explicit `--ref` is required: the CLI does not guess the default branch. To page through the same snapshot, use a commit or tree SHA, not a moving branch.

```sh
gc repo read-dir --ref main -R team/project
gc repo read-dir scripts/MemSnapDump -R Ascend/msinsight --ref 7fe24b3805ade9beb48e55f354315960567443d3 --per-page 3
gc repo read-dir scripts/MemSnapDump -R Ascend/msinsight --ref 7fe24b3805ade9beb48e55f354315960567443d3 --per-page 3 --page 2
```

By default, a valid read makes one [GitCode Tree GET](https://docs.gitcode.com/en/docs/apis/get-api-v-5-repos-owner-repo-git-trees-sha/), never recursive. By default each stdout line contains `MODE TYPE SHA<TAB>PATH` in UTF-8; a link or submodule is listed, never followed. Paths are relative to the requested ref's root. A commit plus a directory filter returns the full child paths; reading a subtree by its SHA alone returns paths inside that tree.

- `--page` starts at 1; `--per-page` defaults to 20 (1–100). A full page suggests trying the next page with the **same page size and immutable ref**. It does not prove another entry exists. The final page can be empty when the total is an exact multiple.
- An empty filtered first page does **not** prove a directory exists: the provider may return the same empty page for a file or missing path. The CLI exits nonzero. List the parent at the same commit and check its entry's type to distinguish these cases. On an empty later page, stdout has no lines in the default format (or `[]` in JSON mode), and stderr describes the ambiguity.
- Without `--all`, the CLI never requests another page. Neither mode uses a Contents fallback or follows redirects. Error bodies are not printed. Oversized, truncated, compressed, inconsistent or unsafe responses fail without printing a partial page.
- This is a direct `gc` command, not a [gh proxy mapping](https://cli.github.com/manual/gh_repo_read-dir). It does not implement the full gh field set, jq or templates.

## Read a complete tree without cloning

Use `--all` with the **directory's tree SHA**, not a branch, tag or commit. For example, first list the parent directory at a commit and take the `gitSHA` of the child whose `gitType` is `tree`. Then use that SHA without a path:

```sh
gc repo read-dir scripts -R Ascend/msinsight --ref 7fe24b3805ade9beb48e55f354315960567443d3 --json name,gitType,gitSHA
gc repo read-dir -R Ascend/msinsight --ref "$tree_sha" --all --per-page 100 --json path,gitType
```

In the second call paths are relative to that tree, not the commit root. To list the repository root with `--all`, use the commit's root **tree** SHA. A branch, abbreviated SHA, directory path or explicit `--page` is not supported in this mode.

The CLI starts at page 1 and makes at most **10** non-recursive requests (at most 2 MiB each). With the default page size of 20, this fits 200 children; use `--per-page 100` for up to 1,000. It buffers all rows in provider order and independently reconstructs the Git tree SHA-1 using every child's name, mode and object ID. An empty or short page alone is not evidence of completeness. Unless the resulting object matches the exact requested SHA, nothing is printed. A duplicate, provider error, truncation or unverified result at the limit also fails without a partial listing. Use the manual page mode if the tree exceeds the limit.

## JSON output

Put `--json` after the optional path to print all four fields, or pass a comma-separated selection:

```sh
gc repo read-dir scripts/MemSnapDump -R Ascend/msinsight --ref 7fe24b3805ade9beb48e55f354315960567443d3 --json
gc repo read-dir --ref main -R team/project --json path,gitSHA
```

Stdout is a single UTF-8 array for the requested page (or verified complete tree with `--all`), in provider order. Each object contains only the selected keys, in selector order:

- `name`: immediate child name; `path`: its exact path relative to the requested ref's root.
- `gitSHA`: the child's Git object ID from the entry's native `sha`, not the requested ref or the enclosing tree ID.
- `gitType`: the native Git object type, checked against its mode: `blob`, `tree` or `commit`. A symlink is a blob; a submodule entry is a commit.

No file sizes, content or inferred metadata are emitted. All rows (including unselected fields needed to validate identity) must pass validation before any output. In manual page mode, page bounds, the ambiguous filtered first-page error, and continuation hints on stderr are unchanged.
