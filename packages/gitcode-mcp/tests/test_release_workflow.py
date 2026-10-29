"""Exercise the actual credential-free inline publication guards from the workflow."""

import hashlib
import json
import subprocess
import textwrap
from pathlib import Path

import pytest

WORKFLOW = Path(__file__).resolve().parents[3] / ".github/workflows/publish-mcp.yml"
SOURCE_SHA = "a" * 40


def inline_guard(step_name):
    step = WORKFLOW.read_text().split(f"      - name: {step_name}\n", 1)[1]
    body = step.split("python -I - <<'PYCODE'\n", 1)[1].split("\n          PYCODE", 1)[0]
    return compile(textwrap.dedent(body), str(WORKFLOW), "exec")


def run_guard(name):
    exec(inline_guard(name), {"__name__": "__main__"})


@pytest.mark.parametrize(("identifier", "digest"), [("", "a" * 64), ("1,2", "a" * 64), ("42", "")])
def test_download_cannot_fall_back_to_all_artifacts(monkeypatch, identifier, digest):
    monkeypatch.setenv("RELEASE_ARTIFACT_ID", identifier)
    monkeypatch.setenv("RELEASE_MANIFEST_SHA256", digest)
    with pytest.raises(AssertionError):
        run_guard("Require immutable producer outputs before downloading anything")


def test_single_immutable_producer_output_is_accepted(monkeypatch):
    monkeypatch.setenv("RELEASE_ARTIFACT_ID", "42")
    monkeypatch.setenv("RELEASE_MANIFEST_SHA256", "a" * 64)
    run_guard("Require immutable producer outputs before downloading anything")


@pytest.fixture
def downloaded(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    root = tmp_path / "release"
    dist = root / "dist"
    dist.mkdir(parents=True)
    files = {}
    for name in (
        "codeasier_gitcode_mcp-0.3.0-py3-none-any.whl",
        "codeasier_gitcode_mcp-0.3.0.tar.gz",
    ):
        content = ("synthetic accepted bytes " + name).encode()
        (dist / name).write_bytes(content)
        files[name] = hashlib.sha256(content).hexdigest()
    data = {
        "schema": 1,
        "package": "codeasier-gitcode-mcp",
        "version": "0.3.0",
        "source_sha": SOURCE_SHA,
        "files": files,
    }
    manifest = root / "manifest.json"
    manifest.write_text(json.dumps(data))
    monkeypatch.setenv("EXPECTED_VERSION", "0.3.0")
    monkeypatch.setenv("EXPECTED_SOURCE_SHA", SOURCE_SHA)
    monkeypatch.setenv(
        "EXPECTED_MANIFEST_SHA256", hashlib.sha256(manifest.read_bytes()).hexdigest()
    )
    return root, data


def test_inline_publication_guard_accepts_only_bound_original_bytes(downloaded):
    run_guard("Fail closed if downloaded artifacts differ from the accepted manifest")


@pytest.mark.parametrize("change", ["bytes", "manifest", "both", "extra", "symlink", "source"])
def test_inline_publication_guard_fails_closed(downloaded, monkeypatch, change):
    root, data = downloaded
    archive = root / "dist" / next(iter(data["files"]))
    if change in {"bytes", "both"}:
        archive.write_bytes(b"replaced")
    if change in {"manifest", "both"}:
        data["files"][archive.name] = hashlib.sha256(archive.read_bytes()).hexdigest()
        data["ignored"] = "changed"
        (root / "manifest.json").write_text(json.dumps(data))
    elif change == "extra":
        (root / "dist" / "extra.whl").touch()
    elif change == "symlink":
        target = root.parent / "replacement"
        archive.rename(target)
        archive.symlink_to(target)
    elif change == "source":
        monkeypatch.setenv("EXPECTED_SOURCE_SHA", "b" * 40)
    with pytest.raises(AssertionError):
        run_guard("Fail closed if downloaded artifacts differ from the accepted manifest")


@pytest.mark.parametrize(
    "change", [None, "repository", "updated_tag", "deleted_tag", "forced_tag", "bad_ref"]
)
def test_release_event_guard_requires_new_canonical_repository_tag(tmp_path, monkeypatch, change):
    payload = {"created": True, "deleted": False, "forced": False, "before": "0" * 40}
    monkeypatch.setenv("GITHUB_REPOSITORY", "codeasier/gitcode-cli")
    monkeypatch.setenv("GITHUB_EVENT_NAME", "push")
    monkeypatch.setenv("GITHUB_REF_TYPE", "tag")
    monkeypatch.setenv("GITHUB_REF", "refs/tags/mcp-v0.3.0")
    if change == "repository":
        monkeypatch.setenv("GITHUB_REPOSITORY", "other/gitcode-cli")
    elif change == "updated_tag":
        payload["created"] = False
    elif change == "deleted_tag":
        payload["deleted"] = True
    elif change == "forced_tag":
        payload["forced"] = True
    elif change == "bad_ref":
        monkeypatch.setenv("GITHUB_REF", "refs/tags/v0.3.0")
    event = tmp_path / "event.json"
    event.write_text(json.dumps(payload))
    monkeypatch.setenv("GITHUB_EVENT_PATH", str(event))
    guard = "Validate event and current release ref before executing source helpers"
    if change is None:
        run_guard(guard)
    else:
        with pytest.raises(AssertionError):
            run_guard(guard)


@pytest.mark.parametrize("annotated", [False, True])
def test_live_tag_parser_matches_exact_raw_and_optional_peeled_refs(annotated):
    prefix = 'awk -v ref="$GITHUB_REF" \''
    programs = [part.split("')\"", 1)[0] for part in WORKFLOW.read_text().split(prefix)[1:]]
    assert len(programs) == 2 and programs[0] == programs[1]
    ref = "refs/tags/mcp-v0.3.0"
    lines = f"{'b' * 40}\t{ref}\n"
    if annotated:
        lines += f"{SOURCE_SHA}\t{ref}^{{}}\n"
    result = subprocess.run(
        ["awk", "-v", f"ref={ref}", programs[0]], input=lines, text=True, capture_output=True
    )
    assert result.returncode == 0
    assert result.stdout.strip() == (SOURCE_SHA if annotated else "b" * 40)


@pytest.mark.parametrize("kind", ["collision", "extra", "duplicate", "peel_only", "malformed"])
def test_live_tag_parser_rejects_ambiguous_or_missing_exact_ref(kind):
    program = WORKFLOW.read_text().split('awk -v ref="$GITHUB_REF" \'', 1)[1].split("')\"", 1)[0]
    ref = "refs/tags/mcp-v0.3.0"
    exact = f"{SOURCE_SHA}\t{ref}\n"
    collision = f"{SOURCE_SHA}\trefs/tags/other/{ref}\n"
    lines = {
        "collision": collision,
        "extra": exact + collision,
        "duplicate": exact + exact,
        "peel_only": f"{SOURCE_SHA}\t{ref}^{{}}\n",
        "malformed": f"not-a-sha\t{ref}\n",
    }[kind]
    result = subprocess.run(
        ["awk", "-v", f"ref={ref}", program], input=lines, text=True, capture_output=True
    )
    assert result.returncode != 0
