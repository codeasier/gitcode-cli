"""Attachment identity checks for local release checksums."""

import pytest

from gitcode_cli.errors import GCError
from gitcode_cli.release_assets import is_archive, named_checksum

OWNER, REPO = "Owner", "project"
TAG, NAME = "release/v1", "résumé %2F.zip"
BASE = f"https://gitcode.com/{OWNER}/{REPO}/releases/download/"
FILE_SEGMENT = "r%C3%A9sum%C3%A9%20%252F.zip"
DIGEST = "a" * 64


@pytest.mark.parametrize("tag_path", ("release/v1", "release%2Fv1"))
def test_attach_route_quotes_only_local_components(tag_path):
    row = {
        "type": "attach",
        "name": NAME,
        "id": 1,
        "digest": DIGEST,
        "browser_download_url": f"{BASE}{tag_path}/{FILE_SEGMENT}",
    }
    assert named_checksum({"assets": [row]}, NAME, owner=OWNER, repo=REPO, tag=TAG) == (None, DIGEST)


def test_attach_route_does_not_override_shared_classifier():
    row = {
        "type": "attach",
        "name": NAME,
        "id": 1,
        "digest": DIGEST,
        "browser_download_url": f"{BASE}release/v1/{FILE_SEGMENT}",
    }
    with pytest.raises(GCError, match="Unrecognized release asset type or route"):
        is_archive(row)


@pytest.mark.parametrize("url", (f"{BASE}release/v1/r%C3%A9sum%C3%A9%20%2F.zip", f"{BASE}release/v1/{FILE_SEGMENT}?"))
def test_attach_route_rejects_noncanonical_filename_or_delimiter(url):
    row = {"type": "attach", "name": NAME, "id": 1, "digest": DIGEST, "browser_download_url": url}
    with pytest.raises(GCError, match="No identified uploaded attachment"):
        named_checksum({"assets": [row]}, NAME, owner=OWNER, repo=REPO, tag=TAG)
