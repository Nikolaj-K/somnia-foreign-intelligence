"""
What: HTTP wrapper for collection-aware ERC-721 ownership checks.
Run:  flask --app wrapper.app run --host 127.0.0.1 --port 8080
Deps: Flask and web3.py; install with `python -m pip install -r requirements.txt`.

Endpoint:
    GET /owns?collectionId=1&wallet=0x...&tokenId=777

If collectionId is omitted, the wrapper defaults to Quills Adventure
collectionId=1 for compatibility with the first demo. The Somnia JSON API
agent should select `votingPower` with fetchUint(string,string,uint8). `owns`
and `ownsInt` remain in the response for human readability and older tools.
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass
from typing import Any
from typing import Optional

from flask import Flask
from flask import jsonify
from flask import request
from web3 import Web3


WALLET_PATTERN = re.compile(r"^0x[a-fA-F0-9]{40}$")
DEFAULT_QUILLS_RPC_URL = "https://api.infra.mainnet.somnia.network/"
DEFAULT_BAYC_RPC_URL = "https://ethereum-rpc.publicnode.com"
QUILLS_NFT_CONTRACT = "0x90780d0641a6328719a636ab289175e2155328a3"
BAYC_NFT_CONTRACT = "0xbc4ca0eda7647a8ab7c2061c2e118a18a936f13d"
ERC721_OWNER_OF_ABI = [
    {
        "type": "function",
        "name": "ownerOf",
        "stateMutability": "view",
        "inputs": [{"name": "tokenId", "type": "uint256"}],
        "outputs": [{"name": "owner", "type": "address"}],
    }
]


class WrapperConfigError(Exception):
    """Raised when required wrapper environment is missing or malformed."""


@dataclass(frozen=True)
class CollectionConfig:
    collection_id: int
    short_label: str
    target_collection_label: str
    target_chain_label: str
    target_nft_contract: str
    target_rpc_url: str
    voting_power: int

    def validated(self) -> "CollectionConfig":
        if not self.target_rpc_url.startswith(("http://", "https://")):
            raise WrapperConfigError(
                f"invalid_rpc_url_for_collection:{self.collection_id}"
            )
        if not is_address_like(self.target_nft_contract):
            raise WrapperConfigError(
                f"invalid_nft_contract_for_collection:{self.collection_id}"
            )
        if self.voting_power <= 0:
            raise WrapperConfigError(
                f"invalid_voting_power_for_collection:{self.collection_id}"
            )
        return CollectionConfig(
            collection_id=self.collection_id,
            short_label=self.short_label,
            target_collection_label=self.target_collection_label,
            target_chain_label=self.target_chain_label,
            target_nft_contract=Web3.to_checksum_address(self.target_nft_contract),
            target_rpc_url=self.target_rpc_url,
            voting_power=self.voting_power,
        )


@dataclass(frozen=True)
class CollectionRegistry:
    collections: dict[int, CollectionConfig]

    @classmethod
    def from_env(cls) -> "CollectionRegistry":
        # TARGET_* keeps old single-collection Cloud Run configs useful for
        # collectionId=1 while QUILLS_* is the new explicit name.
        quills = CollectionConfig(
            collection_id=1,
            short_label="quills",
            target_collection_label="quills-adventure",
            target_chain_label="somnia-mainnet",
            target_nft_contract=os.environ.get(
                "QUILLS_NFT_CONTRACT",
                os.environ.get("TARGET_NFT_CONTRACT", QUILLS_NFT_CONTRACT),
            ),
            target_rpc_url=os.environ.get(
                "QUILLS_RPC_URL",
                os.environ.get("TARGET_RPC_URL", DEFAULT_QUILLS_RPC_URL),
            ),
            voting_power=1,
        ).validated()
        bayc = CollectionConfig(
            collection_id=2,
            short_label="bayc",
            target_collection_label="bored-ape-yacht-club",
            target_chain_label="ethereum-mainnet",
            target_nft_contract=os.environ.get(
                "BAYC_NFT_CONTRACT",
                BAYC_NFT_CONTRACT,
            ),
            target_rpc_url=os.environ.get("BAYC_RPC_URL", DEFAULT_BAYC_RPC_URL),
            voting_power=2,
        ).validated()
        return cls(collections={1: quills, 2: bayc})

    def get(self, collection_id: int) -> Optional[CollectionConfig]:
        return self.collections.get(collection_id)


@dataclass(frozen=True)
class OwnershipResult:
    owns: bool
    wallet: str
    owner: Optional[str]
    token_id: str
    checked_block: Optional[int]
    collection: CollectionConfig

    @property
    def voting_power(self) -> int:
        return self.collection.voting_power if self.owns else 0


class OwnershipChecker:
    """Small ERC-721 ownerOf adapter used by the HTTP endpoint."""

    def __init__(self) -> None:
        self._clients: dict[int, tuple[Web3, Any]] = {}

    def _client_for(self, collection: CollectionConfig) -> tuple[Web3, Any]:
        cached = self._clients.get(collection.collection_id)
        if cached is not None:
            return cached
        web3 = Web3(
            Web3.HTTPProvider(collection.target_rpc_url, request_kwargs={"timeout": 15})
        )
        contract = web3.eth.contract(
            address=Web3.to_checksum_address(collection.target_nft_contract),
            abi=ERC721_OWNER_OF_ABI,
        )
        self._clients[collection.collection_id] = (web3, contract)
        return web3, contract

    def check(
        self,
        collection: CollectionConfig,
        wallet: str,
        token_id: int,
    ) -> OwnershipResult:
        web3, contract = self._client_for(collection)
        assert web3.is_connected(), "target_rpc_unreachable"
        owner = contract.functions.ownerOf(token_id).call()
        owner_checksum = Web3.to_checksum_address(owner)
        wallet_checksum = Web3.to_checksum_address(wallet)
        checked_block = int(web3.eth.block_number)
        return OwnershipResult(
            owns=owner_checksum.lower() == wallet_checksum.lower(),
            wallet=wallet_checksum,
            owner=owner_checksum,
            token_id=str(token_id),
            checked_block=checked_block,
            collection=collection,
        )


def create_app(
    checker: Optional[Any] = None,
    registry: Optional[CollectionRegistry] = None,
) -> Flask:
    app = Flask(__name__)
    app.config["OWNERSHIP_CHECKER"] = checker
    app.config["COLLECTION_REGISTRY"] = registry

    @app.after_request
    def add_no_store_headers(response: Any) -> Any:
        response.headers["Cache-Control"] = "no-store"
        return response

    @app.get("/health")
    def health() -> Any:
        return jsonify({"ok": True, "service": "somnia-ownership-wrapper"})

    @app.get("/owns")
    def owns() -> Any:
        collection_id, collection_error = parse_collection_id(
            request.args.get("collectionId")
        )
        if collection_error is not None:
            return json_error(
                wallet=request.args.get("wallet", ""),
                token_id=request.args.get("tokenId", ""),
                error=collection_error,
                status_code=400,
                collection_id=collection_id,
            )

        try:
            collection = get_registry(app).get(collection_id)
        except WrapperConfigError as exc:
            return json_error(
                wallet=request.args.get("wallet", ""),
                token_id=request.args.get("tokenId", ""),
                error=str(exc),
                status_code=500,
                collection_id=collection_id,
            )
        if collection is None:
            return json_error(
                wallet=request.args.get("wallet", ""),
                token_id=request.args.get("tokenId", ""),
                error="unsupported_collection_id",
                status_code=400,
                collection_id=collection_id,
            )

        wallet_raw = request.args.get("wallet", "")
        token_id_raw = request.args.get("tokenId", "")

        wallet_error = validate_wallet(wallet_raw)
        if wallet_error is not None:
            return json_error(
                wallet_raw, token_id_raw, wallet_error, collection=collection
            )

        token_id, token_error = parse_token_id(token_id_raw)
        if token_error is not None:
            return json_error(
                wallet_raw, token_id_raw, token_error, collection=collection
            )

        try:
            active_checker = get_checker(app)
            result = active_checker.check(collection, wallet_raw, token_id)
        except WrapperConfigError as exc:
            return json_error(wallet_raw, token_id_raw, str(exc), collection=collection)
        except AssertionError as exc:
            return json_error(
                wallet_raw,
                token_id_raw,
                str(exc) or "target_rpc_error",
                collection=collection,
            )
        except Exception:
            return json_error(
                wallet_raw,
                token_id_raw,
                "ownerOf_reverted",
                collection=collection,
            )

        return jsonify(ownership_json(result))

    return app


def get_registry(app: Flask) -> CollectionRegistry:
    registry = app.config.get("COLLECTION_REGISTRY")
    if registry is None:
        registry = CollectionRegistry.from_env()
        app.config["COLLECTION_REGISTRY"] = registry
    return registry


def get_checker(app: Flask) -> Any:
    checker = app.config.get("OWNERSHIP_CHECKER")
    if checker is None:
        checker = OwnershipChecker()
        app.config["OWNERSHIP_CHECKER"] = checker
    return checker


def parse_collection_id(raw_value: Optional[str]) -> tuple[int, Optional[str]]:
    if raw_value in (None, ""):
        return 1, None
    if not raw_value.isdigit():
        return 0, "invalid_collection_id"
    return int(raw_value), None


def validate_wallet(wallet: str) -> Optional[str]:
    if not wallet:
        return "missing_wallet"
    if not is_address_like(wallet):
        return "invalid_wallet"
    return None


def is_address_like(value: str) -> bool:
    return bool(WALLET_PATTERN.match(value))


def parse_token_id(token_id_raw: str) -> tuple[int, Optional[str]]:
    if token_id_raw == "":
        return 0, "missing_token_id"
    if not token_id_raw.isdigit():
        return 0, "invalid_token_id"
    return int(token_id_raw), None


def ownership_json(result: OwnershipResult) -> dict[str, Any]:
    collection = result.collection
    return {
        "ok": True,
        "collectionId": collection.collection_id,
        "collection": collection.short_label,
        "wallet": result.wallet,
        "tokenId": result.token_id,
        "owner": result.owner,
        "owns": result.owns,
        "ownsInt": 1 if result.owns else 0,
        "votingPower": result.voting_power,
        "targetChain": collection.target_chain_label,
        "targetCollection": collection.target_collection_label,
        "targetNftContract": collection.target_nft_contract,
        "checkedBlock": result.checked_block,
    }


def json_error(
    wallet: str,
    token_id: str,
    error: str,
    status_code: int = 200,
    collection_id: Optional[int] = None,
    collection: Optional[CollectionConfig] = None,
) -> Any:
    if collection is not None:
        collection_id = collection.collection_id
        short_label = collection.short_label
        target_chain = collection.target_chain_label
        target_collection = collection.target_collection_label
        target_contract = collection.target_nft_contract
    else:
        short_label = None
        target_chain = None
        target_collection = None
        target_contract = None

    return (
        jsonify(
            {
                "ok": False,
                "collectionId": collection_id,
                "collection": short_label,
                "wallet": wallet,
                "tokenId": token_id,
                "owner": None,
                "owns": False,
                "ownsInt": 0,
                "votingPower": 0,
                "targetChain": target_chain,
                "targetCollection": target_collection,
                "targetNftContract": target_contract,
                "checkedBlock": None,
                "error": error,
            }
        ),
        status_code,
    )


app = create_app()


if __name__ == "__main__":
    port = int(os.environ.get("PORT", "8080"))
    app.run(host="0.0.0.0", port=port)
