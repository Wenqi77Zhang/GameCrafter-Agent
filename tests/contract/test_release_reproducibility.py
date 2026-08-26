import json
import re
import tomllib
from pathlib import Path

from gamecrafter import __version__

ROOT = Path(__file__).resolve().parents[2]
EXPECTED_VERSION = "1.0.0"


def _dependency_name(requirement: str) -> str:
    return re.split(r"\[|[<>=!~; ]", requirement, maxsplit=1)[0].lower().replace("_", "-")


def test_release_versions_are_aligned() -> None:
    project = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    root_package = json.loads((ROOT / "package.json").read_text(encoding="utf-8"))
    web_package = json.loads((ROOT / "apps/web/package.json").read_text(encoding="utf-8"))
    uv_lock = (ROOT / "uv.lock").read_text(encoding="utf-8")

    assert __version__ == EXPECTED_VERSION
    assert project["project"]["version"] == EXPECTED_VERSION
    assert root_package["version"] == EXPECTED_VERSION
    assert web_package["version"] == EXPECTED_VERSION
    assert re.search(rf'name = "gamecrafter"\s+version = "{re.escape(EXPECTED_VERSION)}"', uv_lock)


def test_python_exports_pin_versions_and_artifact_hashes() -> None:
    for filename in ("requirements.lock", "requirements-dev.lock"):
        content = (ROOT / filename).read_text(encoding="utf-8")
        starts = list(re.finditer(r"(?m)^([a-z0-9][a-z0-9._-]*)==[^\s\\]+", content))
        assert starts
        for index, match in enumerate(starts):
            end = starts[index + 1].start() if index + 1 < len(starts) else len(content)
            assert "--hash=sha256:" in content[match.start() : end], match.group(1)


def test_locked_exports_cover_every_direct_dependency() -> None:
    project = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))["project"]
    production = (ROOT / "requirements.lock").read_text(encoding="utf-8")
    development = (ROOT / "requirements-dev.lock").read_text(encoding="utf-8")
    production_names = set(re.findall(r"(?m)^([a-z0-9][a-z0-9._-]*)==", production))
    development_names = set(re.findall(r"(?m)^([a-z0-9][a-z0-9._-]*)==", development))

    direct = {_dependency_name(requirement) for requirement in project["dependencies"]}
    dev = {_dependency_name(requirement) for requirement in project["optional-dependencies"]["dev"]}
    assert direct <= production_names
    assert direct | dev <= development_names


def test_local_setup_and_startup_consume_the_reproducible_release() -> None:
    setup = (ROOT / "scripts/setup.ps1").read_text(encoding="utf-8")
    production = (ROOT / "scripts/production.ps1").read_text(encoding="utf-8")
    doctor = (ROOT / "scripts/doctor.ps1").read_text(encoding="utf-8")

    assert "--require-hashes -r requirements-dev.lock" in setup
    assert "install --frozen-lockfile" in setup
    assert "--wait --wait-timeout" in production
    assert 'expectedVersion = "1.0.0"' in doctor
    assert 'expectedPhase = "M14-local"' in doctor


def test_remote_build_inputs_are_immutable() -> None:
    dockerfiles = [ROOT / "deploy/Dockerfile.api", ROOT / "deploy/Dockerfile.web"]
    for dockerfile in dockerfiles:
        for line in dockerfile.read_text(encoding="utf-8").splitlines():
            if line.startswith("FROM "):
                assert re.search(r"@sha256:[0-9a-f]{64}(?:\s|$)", line), line

    for filename in ("compose.yaml", "compose.production.yaml", ".github/workflows/verify.yml"):
        content = (ROOT / filename).read_text(encoding="utf-8")
        assert re.search(r"pgvector/pgvector:[^\s]+@sha256:[0-9a-f]{64}", content)

    workflow = (ROOT / ".github/workflows/verify.yml").read_text(encoding="utf-8")
    action_uses = re.findall(r"uses:\s*[^@\s]+@([^\s#]+)", workflow)
    assert action_uses
    assert all(re.fullmatch(r"[0-9a-f]{40}", revision) for revision in action_uses)
