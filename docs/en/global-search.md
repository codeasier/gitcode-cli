# Global search

Use `gc search repos`, `gc search issues`, `gc search prs`, and `gc search users`
for keyword search. The available filters, sort fields, and JSON fields are
listed by each command's `--help`. Search does not interpret GitHub's raw
qualifier syntax.

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
