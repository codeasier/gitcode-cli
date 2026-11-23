# Read a repository file without cloning

```sh
gc repo read-file README.md -R team/project
gc repo read-file 'art/棋子 #1.png' -R team/project --ref 'topic/assets' -o token.png
```

Omit `-R` for a canonical GitCode HTTPS or SSH origin. Pass a decoded, repository-relative path; spaces, Unicode and literal percent signs are filename data. Omit `--ref` to use the provider's default branch, or pin a commit for reproducible reads. A single [GitCode v5 Contents GET](https://docs.gitcode.com/docs/apis/get-api-v-5-repos-owner-repo-contents-path/) must return a regular file at that path, with canonical Base64, matching byte count and Git blob SHA. When configured, the token is sent only in the [v5 Authorization Bearer header](https://docs.gitcode.com/docs/apis/#authorization), never in the URL. No directory traversal, redirects, raw download URLs, retries or alternate ref lookups. The CLI accepts files up to 1 MiB and response bodies up to 2 MiB.

Stdout (including pipes) preserves UTF-8 text bytes, tabs and line endings, without adding a newline. Binary or unsafe control characters require `-o/--output`. On POSIX, choose a **new** file under an existing trusted directory with no symlink components; the completed file appears atomically and existing destinations are never overwritten.

This is a direct `gc` subset of [the preview gh command](https://cli.github.com/manual/gh_repo_read-file), not a transparent proxy mapping. It does not launch a pager, render JSON, allow unsafe terminal output, follow large-file pointers, or implement `--clobber`.
