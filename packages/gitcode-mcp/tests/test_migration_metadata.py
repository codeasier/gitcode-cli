"""Keep the immutable legacy dependency distinct from the candidate at MCP 0.3.0."""

import importlib.util
import sys
from pathlib import Path
from types import SimpleNamespace

import anyio
import pytest

import gitcode_mcp

SCRIPT = Path(__file__).resolve().parents[1] / "scripts/migration_acceptance.py"
SPEC = importlib.util.spec_from_file_location("migration_acceptance_metadata", SCRIPT)
acceptance = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(acceptance)


@pytest.fixture
def installed(monkeypatch):
    """Synthetic metadata only: never install a distribution or open OAuth state."""

    def configure(cli_version, requirement=None):
        monkeypatch.setattr(acceptance, "VERSION", "0.3.0")
        monkeypatch.setattr(gitcode_mcp, "__version__", "0.3.0")
        distribution = SimpleNamespace(
            version=acceptance.VERSION,
            metadata={"Requires-Python": ">=3.11"},
            requires=[requirement or f"pygitcode=={cli_version}"],
            entry_points=[
                SimpleNamespace(
                    group="console_scripts", name=name, value=f"gitcode_mcp.{module}:main"
                )
                for name, module in (("gitcode-mcp", "__main__"), ("gitcode-clone", "clone"))
            ],
        )
        monkeypatch.setattr(acceptance.importlib.metadata, "distribution", lambda _: distribution)
        monkeypatch.setattr(acceptance.importlib.metadata, "version", lambda _: cli_version)
        monkeypatch.setattr(
            gitcode_mcp, "__file__", str(Path(sys.prefix) / "synthetic-mcp" / "__init__.py")
        )

    return configure


@pytest.mark.parametrize("legacy", [False, True])
@pytest.mark.parametrize("cli_version", ["0.1.6", "0.1.7"])
def test_metadata_requires_the_exact_dependency_for_its_role(installed, legacy, cli_version):
    installed(cli_version)
    expected = "0.1.6" if legacy else "0.1.7"
    if cli_version == expected:
        acceptance.installed_metadata(legacy=legacy)
    else:
        with pytest.raises(AssertionError):
            acceptance.installed_metadata(legacy=legacy)


@pytest.mark.parametrize(
    ("legacy", "cli_version", "requirement"),
    [
        (True, "0.1.6", "pygitcode==0.1.7"),
        (False, "0.1.7", "pygitcode==0.1.6"),
        (True, "0.1.6", "pygitcode>=0.1.6"),
        (False, "0.1.7", "pygitcode>=0.1.7"),
    ],
)
def test_metadata_rejects_wrong_or_loosened_declared_pin(
    installed, legacy, cli_version, requirement
):
    installed(cli_version, requirement)
    with pytest.raises(AssertionError):
        acceptance.installed_metadata(legacy=legacy)


@pytest.mark.parametrize("mode", ["seed", "smoke", "verify"])
@pytest.mark.parametrize("cli_version", ["0.1.6", "0.1.7"])
def test_entry_point_selects_legacy_only_for_seed(
    installed, monkeypatch, tmp_path, mode, cli_version
):
    installed(cli_version)
    completed = []
    monkeypatch.setattr(sys, "argv", [str(SCRIPT), mode, str(tmp_path / "fixture")])
    monkeypatch.setattr(acceptance, "isolate_process", lambda: None)
    monkeypatch.setattr(acceptance, "smoke", lambda: completed.append("smoke"))
    monkeypatch.setattr(anyio, "run", lambda operation, _: completed.append(operation.__name__))
    expected = "0.1.6" if mode == "seed" else "0.1.7"
    if cli_version == expected:
        acceptance.main()
        assert completed == [mode]
    else:
        with pytest.raises(AssertionError):
            acceptance.main()
        assert not completed
