# Global search

Use `gc search repos`, `gc search issues`, `gc search prs`, and `gc search users`
for keyword search. The available filters, sort fields, and JSON fields are
listed by each command's `--help`. Search does not interpret GitHub's raw
qualifier syntax.

```bash
gc search repos parser --include-forks false --sort stars --order desc --json fullName,isFork,watchersCount
```

By default, `gc search repos` uses the [repository search endpoint][gitcode-repos]
without a fork filter. To request only original repositories, pass
`--include-forks false`. This sends `fork=false` on each page and fails without
printing results if a returned row is a fork or lacks a definite non-fork
marker. It does not guarantee that every matching repository is indexed.

`--json isFork` reports the fork marker on each returned row, not whether forks
were included in the index. A boolean or integer 0/1 becomes a JSON boolean;
a missing or unrecognized marker becomes `null` in an unfiltered search.

Two modes are unavailable: including forks alongside originals (or selecting
only forks), and sorting by watch count. The [AtomGit reference][repos]
describes both inclusion and watch sorting, but in [live GitCode verification][live]
the inclusion request omitted known matches, and the watch sort returned the
same non-monotonic counts in both orders. The [GitCode reference][gitcode-repos]
also restricts fork inclusion and does not list a watch sort. The CLI rejects
these modes before searching rather than printing incomplete or misordered
results. `watchersCount` remains available as a JSON output field. Repository
search is direct-only, not available through the gh proxy.

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
[gitcode-repos]: https://docs.gitcode.com/docs/apis/get-api-v-5-search-repositories/
[live]: https://github.com/codeasier/gitcode-cli/pull/214#issuecomment-7126159859
