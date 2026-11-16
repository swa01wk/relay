"""The gateway's layers: controllers → services → repositories, never the other way or around."""

from __future__ import annotations

import ast
from pathlib import Path

PACKAGE = Path(__file__).resolve().parents[1] / "src" / "relay_gateway"

# layer → import prefixes it must not use
FORBIDDEN = {
    # Controllers speak HTTP and call services; no runtime, adapters or stores.
    "controllers": ("relay_runtime", "relay_adapter_", "relay_gateway.repositories", "relay_sdk"),
    # Services hold the logic and stay usable outside a request.
    "services": ("fastapi", "starlette", "relay_gateway.controllers", "relay_gateway.core.container"),
    # Repositories only read and write stores.
    "repositories": ("fastapi", "starlette", "relay_gateway.controllers", "relay_gateway.services",
                     "relay_gateway.core.container"),
}


def _imports(path: Path) -> set[str]:
    names: set[str] = set()
    for node in ast.walk(ast.parse(path.read_text())):
        if isinstance(node, ast.Import):
            names.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            names.add(node.module)
    return names


def test_layers_only_depend_downwards():
    problems = []
    for layer, forbidden in FORBIDDEN.items():
        files = sorted((PACKAGE / layer).glob("*.py"))
        assert files, layer
        for path in files:
            for name in _imports(path):
                if name.startswith(forbidden):
                    problems.append(f"{layer}/{path.name} imports {name}")
    assert problems == []
