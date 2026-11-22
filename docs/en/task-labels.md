# Repository task labels

`gc label` manages the task-label catalog of a GitCode repository. It does not
apply labels to individual issues or PRs.

```sh
gc label list -R OWNER/REPO --search bug --json name,color
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

Use these commands as `gc` or `gitcode`; the optional `gh` proxy does not
dispatch them.

Official v5 API: [list][list], [create][create], [update][update], [delete][delete].

[list]: https://docs.gitcode.com/en/docs/apis/get-api-v-5-repos-owner-repo-labels/
[create]: https://docs.gitcode.com/en/docs/apis/post-api-v-5-repos-owner-repo-labels/
[update]: https://docs.gitcode.com/en/docs/apis/patch-api-v-5-repos-owner-repo-labels-original-name/
[delete]: https://docs.gitcode.com/en/docs/apis/delete-api-v-5-repos-owner-repo-labels-name/
