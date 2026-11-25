# Repository task labels

`gc label` manages the task-label catalog of a GitCode repository. It does not
apply labels to individual issues or PRs.

```sh
gc label list -R OWNER/REPO --search bug --json name,color
gc label list -R OWNER/REPO --sort name --order desc --limit 5 --json name
gc label create bug -R OWNER/REPO --color D73A4A
gc label edit bug -R OWNER/REPO --name defect
gc label clone OWNER/SOURCE -R OWNER/DESTINATION
gc label delete defect -R OWNER/REPO
```

Lists filter by a case-insensitive substring of the name. The API provides a
name and color, not a description. For existing labels, `create --force`
updates the color only if one was explicitly supplied. The default clone
adds missing labels; clone with `--force` also updates matching colors.
Cloning never deletes destination-only labels. It checks both complete
catalogs before starting and reports confirmed progress on partial failure.
Deletion prompts for confirmation unless you pass `--yes` and reports
success only after reading back the catalog and confirming absence.

To sort by name, pass `--sort name` and optionally `--order asc|desc`
(default ascending). Names are compared by Unicode code point, case-sensitively,
without locale rules or normalization. Only this mode exhausts the numbered
pages before applying `--limit`: up to 10 data pages of 100 labels (1,000 labels) plus a
terminal empty probe, using fixed-origin GET and Bearer authentication when
configured. Even a short page is probed. Repeated labels, inconsistent counts,
HTTP errors or an unverified end yield no sorted output. Reads across pages
are not an atomic snapshot; use a stable catalog for comparisons.

If both global and subcommand `-R` are provided in sorted mode, they must identify the same repository.
Without `--sort`, existing provider order and name-substring search are
unchanged. Sorting with `--search`, standalone `--order`, and
`--sort created` are unsupported: this API does not return creation times.

Use these commands as `gc` or `gitcode`; the optional `gh` proxy does not
dispatch them.

Official v5 API: [list][list], [create][create], [update][update], [delete][delete].

[list]: https://docs.gitcode.com/en/docs/apis/get-api-v-5-repos-owner-repo-labels/
[create]: https://docs.gitcode.com/en/docs/apis/post-api-v-5-repos-owner-repo-labels/
[update]: https://docs.gitcode.com/en/docs/apis/patch-api-v-5-repos-owner-repo-labels-original-name/
[delete]: https://docs.gitcode.com/en/docs/apis/delete-api-v-5-repos-owner-repo-labels-name/
