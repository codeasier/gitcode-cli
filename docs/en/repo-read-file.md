# Read a repository file without cloning

```sh
gc repo read-file README.md -R team/project
gc repo read-file 'art/棋子 #1.png' -R team/project --ref 'topic/assets' -o token.png
# Refresh a local copy without truncating it during download
gc repo read-file README.md -R team/project --ref main -o snapshot.md --clobber
```

Omit `-R` for a canonical GitCode HTTPS or SSH origin. Pass a decoded, repository-relative path; spaces, Unicode and literal percent signs are filename data. Omit `--ref` to use the provider's default branch, or pin a commit for reproducible reads. A single [GitCode v5 Contents GET](https://docs.gitcode.com/docs/apis/get-api-v-5-repos-owner-repo-contents-path/) must return a regular file at that path, with canonical Base64, matching byte count and Git blob SHA. When configured, the token is sent only in the [v5 Authorization Bearer header](https://docs.gitcode.com/docs/apis/#authorization), never in the URL. No directory traversal, redirects, raw download URLs, retries or alternate ref lookups. The CLI accepts files up to 1 MiB and response bodies up to 2 MiB.

Stdout (including pipes) preserves UTF-8 text bytes, tabs and line endings, without adding a newline. To receive raw binary bytes or unsafe control characters, use `-o/--output`. On POSIX, pass a filename under an existing trusted directory with no symlink components. By default the command never overwrites an existing destination. Use `--clobber` with `-o FILE` to replace that directory entry with the complete, verified file, or create it if missing. A failed fetch, integrity check or staging write leaves the old file intact. The replacement has private permissions (at most `0600`); it does not preserve the old inode, permissions or other metadata, and other hard links keep the old bytes. The command rejects a directory, symlink or special file observed at the destination and never follows a destination symlink. Use a destination path that another process will not concurrently rename or change, including its parent directories: type and path checks are not atomic with replacement. This is local file replacement, not a write to GitCode.

## JSON output

```sh
gc repo read-file README.md -R team/project --json
gc repo read-file README.md -R team/project --json path,size,gitSHA
gc repo read-file 'art/棋子 #1.png' -R team/project --json encoding,content
```

Put a bare `--json` after the path for metadata only: `name`, `path`, `gitSHA`, `size`, `type`, and `encoding`. Or select fields once, comma-separated, to print one UTF-8 JSON object with exactly those keys in order. Size is in bytes; `gitSHA` identifies the Git blob, not a commit. Only inline regular files (`type: "file"`, `encoding: "base64"`) are accepted. Select `content` explicitly to include canonical Base64, even for text files. No raw binary or terminal escape sequences are printed in JSON mode. JSON cannot be combined with `--output`.

Selecting only metadata still validates the entire blob with the same request and limits; an invalid or oversized blob produces no JSON. This direct `gc` command implements a subset of [gh v2.105.0 read-file](https://github.com/cli/cli/blob/v2.105.0/pkg/cmd/repo/read-file/read_file.go), not a transparent proxy mapping. URL fields, jq, templates, a pager, unsafe terminal output, and large-file fallback are not implemented.
