import pytest
from click.testing import CliRunner

from gitcode_cli.cli import main
from gitcode_cli.gh_proxy import ProxyError, validate_gitcode_command


def test_real_entrypoint_exposes_direct_api():
    result = CliRunner().invoke(main, ["api", "--help"])
    assert result.exit_code == 0, result.output
    assert "ENDPOINT" in result.output


def test_raw_api_is_not_transparently_routed_by_gh():
    with pytest.raises(ProxyError, match="refusing to fall back"):
        validate_gitcode_command(["api", "repos/owner/repo"])
