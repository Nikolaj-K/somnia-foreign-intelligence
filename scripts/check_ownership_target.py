"""
What: Read-only sanity check for an ERC-721 target used by the wrapper.
Run:  python scripts/check_ownership_target.py --token-id 1 --token-id 2
Deps: web3.py; install with `python -m pip install -r requirements.txt`.

This script does not use private keys and does not spend funds. It checks RPC
connectivity, target contract bytecode, optional ERC-721 metadata, and ownerOf
for sample token IDs.
"""

from __future__ import annotations

import argparse
import logging
import os
from dataclasses import dataclass
from typing import Any

from rich.logging import RichHandler
from web3 import Web3


LOGGER = logging.getLogger("ownership-target-check")
DEFAULT_RPC_URL = "https://api.infra.mainnet.somnia.network/"
DEFAULT_CONTRACT = "0x90780d0641a6328719a636ab289175e2155328a3"
DEFAULT_TOKEN_IDS = [1, 2, 3, 4, 3333]
ERC721_ABI = [
    {
        "type": "function",
        "name": "name",
        "stateMutability": "view",
        "inputs": [],
        "outputs": [{"type": "string"}],
    },
    {
        "type": "function",
        "name": "symbol",
        "stateMutability": "view",
        "inputs": [],
        "outputs": [{"type": "string"}],
    },
    {
        "type": "function",
        "name": "totalSupply",
        "stateMutability": "view",
        "inputs": [],
        "outputs": [{"type": "uint256"}],
    },
    {
        "type": "function",
        "name": "ownerOf",
        "stateMutability": "view",
        "inputs": [{"name": "tokenId", "type": "uint256"}],
        "outputs": [{"type": "address"}],
    },
]


@dataclass(frozen=True)
class TargetConfig:
    rpc_url: str
    contract_address: str
    token_ids: list[int]


def main() -> None:
    args = parse_args()
    configure_logging()
    config = load_config(args)
    web3 = Web3(Web3.HTTPProvider(config.rpc_url, request_kwargs={"timeout": 20}))
    assert web3.is_connected(), f"Could not connect to RPC: {config.rpc_url}"

    contract_address = Web3.to_checksum_address(config.contract_address)
    chain_id = web3.eth.chain_id
    code = web3.eth.get_code(contract_address)
    assert len(code) > 0, f"No bytecode at target contract: {contract_address}"

    contract = web3.eth.contract(address=contract_address, abi=ERC721_ABI)
    LOGGER.info("rpc_url=%s", config.rpc_url)
    LOGGER.info("chain_id=%s", chain_id)
    LOGGER.info("contract_address=%s", contract_address)
    LOGGER.info("code_bytes=%s", len(code))
    log_optional_call(contract, "name")
    log_optional_call(contract, "symbol")
    log_optional_call(contract, "totalSupply")

    for token_id in config.token_ids:
        try:
            owner = contract.functions.ownerOf(token_id).call()
            LOGGER.info("ownerOf token_id=%s owner=%s", token_id, owner)
        except Exception as exc:
            LOGGER.warning(
                "ownerOf token_id=%s failed error_type=%s error=%s",
                token_id,
                type(exc).__name__,
                str(exc)[:200],
            )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Check ERC-721 ownership target")
    parser.add_argument(
        "--rpc-url",
        default=os.environ.get("TARGET_RPC_URL", DEFAULT_RPC_URL),
    )
    parser.add_argument(
        "--contract",
        default=os.environ.get("TARGET_NFT_CONTRACT", DEFAULT_CONTRACT),
    )
    parser.add_argument(
        "--token-id",
        type=int,
        action="append",
        dest="token_ids",
        help="Token ID to ownerOf-check. Can be repeated.",
    )
    return parser.parse_args()


def load_config(args: argparse.Namespace) -> TargetConfig:
    token_ids = args.token_ids if args.token_ids else DEFAULT_TOKEN_IDS
    assert args.rpc_url.startswith(("http://", "https://")), "RPC URL must be HTTP(S)"
    assert Web3.is_address(args.contract), "Contract address is invalid"
    assert all(
        token_id >= 0 for token_id in token_ids
    ), "Token IDs must be non-negative"
    return TargetConfig(
        rpc_url=args.rpc_url,
        contract_address=args.contract,
        token_ids=token_ids,
    )


def log_optional_call(contract: Any, function_name: str) -> None:
    try:
        value = getattr(contract.functions, function_name)().call()
        LOGGER.info("%s=%s", function_name, value)
    except Exception as exc:
        LOGGER.warning(
            "%s failed error_type=%s error=%s",
            function_name,
            type(exc).__name__,
            str(exc)[:200],
        )


def configure_logging() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(message)s",
        handlers=[RichHandler(rich_tracebacks=True, show_path=False)],
    )


if __name__ == "__main__":
    main()
