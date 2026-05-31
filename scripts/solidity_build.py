"""
What: Shared Solidity compiler resolution and contract compilation helpers.
Run:  Imported by CLI and tests.
Deps: py-solc-x; optional network access only if solc must be installed.

Resolution order:
1. Explicit config path.
2. Repo-local `.solcx/solc-v0.8.20`.
3. Adjacent prior Somnia agents project install, if present.
4. Auto-install into repo-local `.solcx`.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from solcx import compile_standard
from solcx import install_solc


DEFAULT_SOLC_VERSION = "0.8.20"
CONTRACT_PATHS = [
    "contracts/interfaces/ISomniaAgent.sol",
    "contracts/NftGatedVote.sol",
    "contracts/JsonApiUintProbe.sol",
    "contracts/test/MockSomniaAgentPlatform.sol",
]


def resolve_solc_binary(
    project_root: Path,
    configured_path: Any = None,
    allow_install: bool = True,
) -> Path:
    """Resolve a usable solc binary with a portable repo-local fallback."""

    candidates: list[Path] = []
    if configured_path:
        configured = Path(str(configured_path)).expanduser()
        if not configured.is_absolute():
            configured = project_root / configured
        candidates.append(configured)

    repo_solcx_dir = project_root / ".solcx"
    repo_solc_binary = repo_solcx_dir / f"solc-v{DEFAULT_SOLC_VERSION}"
    candidates.append(repo_solc_binary)

    adjacent_solc_binary = (
        project_root.parent
        / "agents"
        / ".solcx"
        / f"solc-v{DEFAULT_SOLC_VERSION}"
    )
    candidates.append(adjacent_solc_binary)

    for candidate in candidates:
        if candidate.exists():
            return candidate

    if allow_install:
        repo_solcx_dir.mkdir(exist_ok=True)
        try:
            install_solc(DEFAULT_SOLC_VERSION, solcx_binary_path=repo_solcx_dir)
        except Exception as exc:
            raise AssertionError(
                "Could not auto-install solc "
                f"{DEFAULT_SOLC_VERSION}. Set `solc_binary` in config.local.json "
                "to an existing compiler path, or run with network access once "
                "so py-solc-x can install it. "
                f"Original error: {exc}"
            ) from exc
        if repo_solc_binary.exists():
            return repo_solc_binary

    searched = ", ".join(str(candidate) for candidate in candidates)
    raise AssertionError(
        f"Missing solc {DEFAULT_SOLC_VERSION}. Searched: {searched}"
    )


def compile_project_contracts(project_root: Path, solc_binary: Path) -> dict[str, Any]:
    """Compile the Solidity files used by the CLI and local tests."""

    sources = {
        path: {"content": (project_root / path).read_text(encoding="utf-8")}
        for path in CONTRACT_PATHS
    }
    return compile_standard(
        {
            "language": "Solidity",
            "sources": sources,
            "settings": {
                "optimizer": {"enabled": True, "runs": 200},
                "outputSelection": {
                    "*": {
                        "*": [
                            "abi",
                            "evm.bytecode.object",
                            "evm.deployedBytecode.object",
                        ]
                    }
                },
            },
        },
        solc_binary=solc_binary,
    )
