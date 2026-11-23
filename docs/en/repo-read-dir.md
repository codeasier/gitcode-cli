# Read one page of a repository directory

List the immediate children of a path without cloning. Omit the path to list the root of a branch, commit or tree SHA. An explicit `--ref` is required: the CLI does not guess the default branch. To page through the same snapshot, use a commit or tree SHA, not a moving branch.

```sh
gc repo read-dir --ref main -R team/project
gc repo read-dir scripts/MemSnapDump -R Ascend/msinsight --ref 7fe24b3805ade9beb48e55f354315960567443d3 --per-page 3
gc repo read-dir scripts/MemSnapDump -R Ascend/msinsight --ref 7fe24b3805ade9beb48e55f354315960567443d3 --per-page 3 --page 2
```

A valid read makes one [GitCode Tree GET](https://atomgit-api-doc.atomgit.com/1.repositories/2.get_repository_directory_tree.html), never recursive. Each stdout line contains `MODE TYPE SHA<TAB>PATH` in UTF-8; a link or submodule is listed, never followed. Paths are relative to the requested ref's root. A commit plus a directory filter returns the full child paths; reading a subtree by its SHA alone returns paths inside that tree.

- `--page` starts at 1; `--per-page` defaults to 20 (1–100). A full page suggests trying the next page with the **same page size and immutable ref**. It does not prove another entry exists. The final page can be empty when the total is an exact multiple.
- An empty filtered first page does **not** prove a directory exists: the provider may return the same empty page for a file or missing path. The CLI exits nonzero. List the parent at the same commit and check its entry's type to distinguish these cases. On an empty later page, stdout is empty and stderr describes the ambiguity.
- No Contents fallback, pagination loop or redirect. Error bodies are not printed. Oversized, truncated, compressed, inconsistent or unsafe responses fail without printing a partial page.
- This is a direct `gc` command, not a [gh proxy mapping](https://cli.github.com/manual/gh_repo_read-dir). It does not implement gh JSON fields, jq or templates.
