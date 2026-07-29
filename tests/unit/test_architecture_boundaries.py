import ast
from pathlib import Path


def test_domain_and_application_do_not_import_outward_frameworks() -> None:
    forbidden = (
        "fastapi",
        "gamecrafter.infrastructure",
        "langgraph",
        "openai",
        "sqlalchemy",
    )
    source_root = Path("src/gamecrafter")
    violations: list[str] = []

    for layer in ("domain", "application"):
        for path in (source_root / layer).rglob("*.py"):
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
            for node in ast.walk(tree):
                modules: list[str] = []
                if isinstance(node, ast.Import):
                    modules.extend(alias.name for alias in node.names)
                elif isinstance(node, ast.ImportFrom) and node.module:
                    modules.append(node.module)
                for module in modules:
                    if module.startswith(forbidden):
                        violations.append(f"{path}:{node.lineno} imports {module}")

    assert violations == []


def test_c2_model_adapters_do_not_import_network_clients() -> None:
    """Keep the confirmed C2 runtime incapable of constructing a paid client."""

    model_root = Path("src/gamecrafter/infrastructure/models")
    forbidden = ("httpx", "openai", "requests")
    violations: list[str] = []

    for path in model_root.rglob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            modules: list[str] = []
            if isinstance(node, ast.Import):
                modules.extend(alias.name for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                modules.append(node.module)
            for module in modules:
                if module.startswith(forbidden):
                    violations.append(f"{path}:{node.lineno} imports {module}")

    assert violations == []
