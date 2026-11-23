# Global search

Use `gc search repos`, `gc search issues`, `gc search prs`, and `gc search users`
for keyword search. The available filters, sort fields, and JSON fields are
listed by each command's `--help`. Search does not interpret GitHub's raw
qualifier syntax.

```bash
gc search repos parser --include-forks true --sort watches --order desc --json fullName,watchersCount
```

Repository search uses the [dedicated repository endpoint][repos]. By default
it omits `fork` (the API excludes forks). Pass `--include-forks true` to
include forks **and** original repositories, or `--include-forks false` to
explicitly exclude forks. Unlike [gh][gh-repos], `only` is not supported.
`--sort watches` sorts by watch count on the server; it is a GitCode option.
These options are for direct `gc search repos` only, not the gh proxy.

The [GitCode reference][legacy-repos] notes that fork inclusion may depend on a
provider allowlist. The CLI keeps its existing bound of 20 repositories per
page and 100 pages. If the server rejects the query, gc reports the error
rather than retrying without the requested options.

```bash
gc search prs "improve telemetry" --sort updated --limit 25 --json number,title,state,repository,url
```

Pull request search uses the [documented typed search endpoint][typed] on
`api.gitcode.com` ([same contract as AtomGit][hosts]). It is not a repository scan.
The endpoint returns open, merged and closed PRs; the command reports these as
`OPEN`, `MERGED`, and `CLOSED`. Dates retain the API's UTC+8 timestamp format.
The search API does not offer a PR state, author or repository filter. To
filter PRs in a particular repository, use `gc pr list -R OWNER/REPO` instead.
For PR details not present in search results, use `gc pr view`.

`gc search prs` requests up to 10 results per page, stopping at the requested
limit (30 by default) or the final API page, with a CLI maximum of 1,000
results. Invalid, incomplete, or overlapping pages cause an error instead of
returning partial success. A configured token is sent only in the
authorization header for this endpoint; without one, results are public.

The [official search API index][index] does not list global code or commit
search operations. Their `gh search` equivalents are not implemented by `gc`.

[typed]: https://atomgit-api-doc.atomgit.com/en/4.search/461.search_by_type.html
[hosts]: https://atomgit-api-doc.atomgit.com/en/guide/1.quick-start.html
[index]: https://atomgit-api-doc.atomgit.com/llms.txt

[repos]: https://atomgit-api-doc.atomgit.com/en/4.search/82.search_repositories.html
[legacy-repos]: https://docs.gitcode.com/docs/apis/get-api-v-5-search-repositories/
[gh-repos]: https://cli.github.com/manual/gh_search_repos
