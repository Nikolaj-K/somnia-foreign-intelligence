"""
What: Local tests for the ownership wrapper HTTP endpoint.
Run:  python -m pytest test/test_wrapper.py
Deps: Flask from requirements.txt.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from wrapper.app import CollectionConfig
from wrapper.app import CollectionRegistry
from wrapper.app import OwnershipResult
from wrapper.app import create_app


VALID_WALLET = "0x1111111111111111111111111111111111111111"
OWNER = "0x1111111111111111111111111111111111111111"
OTHER = "0x2222222222222222222222222222222222222222"
QUILLS_CONTRACT = "0x90780d0641a6328719a636ab289175e2155328a3"
BAYC_CONTRACT = "0xbc4ca0eda7647a8ab7c2061c2e118a18a936f13d"


@dataclass
class FakeChecker:
    owner: Optional[str] = OWNER
    should_raise: bool = False
    seen_collection_ids: list[int] | None = None

    def check(
        self,
        collection: CollectionConfig,
        wallet: str,
        token_id: int,
    ) -> OwnershipResult:
        if self.seen_collection_ids is not None:
            self.seen_collection_ids.append(collection.collection_id)
        if self.should_raise:
            raise RuntimeError("ownerOf reverted")
        owner = self.owner or OTHER
        return OwnershipResult(
            owns=owner.lower() == wallet.lower(),
            wallet=wallet,
            owner=owner,
            token_id=str(token_id),
            checked_block=123,
            collection=collection,
        )


def make_test_registry_has_quills_and_bayc() -> None:
    registry = make_test_registry()

    quills = registry.get(1)
    bayc = registry.get(2)

    assert quills is not None
    assert quills.target_collection_label == "quills-adventure"
    assert quills.target_chain_label == "somnia-mainnet"
    assert quills.voting_power == 1
    assert bayc is not None
    assert bayc.target_collection_label == "bored-ape-yacht-club"
    assert bayc.target_chain_label == "ethereum-mainnet"
    assert bayc.voting_power == 2


def test_health_endpoint_returns_json() -> None:
    app = create_app(checker=FakeChecker(), registry=make_test_registry())
    response = app.test_client().get("/health")
    assert response.status_code == 200
    assert response.get_json() == {"ok": True, "service": "somnia-ownership-wrapper"}
    assert response.headers["Cache-Control"] == "no-store"


def test_quills_owns_true_response_defaults_when_collection_id_missing() -> None:
    seen_collection_ids: list[int] = []
    app = create_app(
        checker=FakeChecker(owner=OWNER, seen_collection_ids=seen_collection_ids),
        registry=make_test_registry(),
    )
    response = app.test_client().get(f"/owns?wallet={VALID_WALLET}&tokenId=1234")
    data = response.get_json()

    assert response.status_code == 200
    assert seen_collection_ids == [1]
    assert data["ok"] is True
    assert data["collectionId"] == 1
    assert data["collection"] == "quills"
    assert data["owns"] is True
    assert data["ownsInt"] == 1
    assert data["votingPower"] == 1
    assert data["wallet"] == VALID_WALLET
    assert data["owner"] == OWNER
    assert data["tokenId"] == "1234"
    assert data["checkedBlock"] == 123
    assert data["targetChain"] == "somnia-mainnet"
    assert data["targetCollection"] == "quills-adventure"
    assert data["targetNftContract"] == QUILLS_CONTRACT


def test_bayc_owns_true_response_has_voting_power_two() -> None:
    app = create_app(checker=FakeChecker(owner=OWNER), registry=make_test_registry())
    response = app.test_client().get(
        f"/owns?collectionId=2&wallet={VALID_WALLET}&tokenId=1234"
    )
    data = response.get_json()

    assert response.status_code == 200
    assert data["ok"] is True
    assert data["collectionId"] == 2
    assert data["collection"] == "bayc"
    assert data["owns"] is True
    assert data["ownsInt"] == 1
    assert data["votingPower"] == 2
    assert data["targetChain"] == "ethereum-mainnet"
    assert data["targetCollection"] == "bored-ape-yacht-club"
    assert data["targetNftContract"] == BAYC_CONTRACT


def test_not_owned_response_has_zero_voting_power() -> None:
    app = create_app(checker=FakeChecker(owner=OTHER), registry=make_test_registry())
    response = app.test_client().get(
        f"/owns?collectionId=2&wallet={VALID_WALLET}&tokenId=1234"
    )
    data = response.get_json()

    assert response.status_code == 200
    assert data["ok"] is True
    assert data["owns"] is False
    assert data["ownsInt"] == 0
    assert data["votingPower"] == 0
    assert data["owner"] == OTHER


def test_invalid_collection_id_returns_clear_400_error() -> None:
    app = create_app(checker=FakeChecker(), registry=make_test_registry())
    response = app.test_client().get(
        f"/owns?collectionId=99&wallet={VALID_WALLET}&tokenId=1234"
    )
    data = response.get_json()

    assert response.status_code == 400
    assert data["ok"] is False
    assert data["collectionId"] == 99
    assert data["votingPower"] == 0
    assert data["error"] == "unsupported_collection_id"


def test_malformed_collection_id_returns_clear_400_error() -> None:
    app = create_app(checker=FakeChecker(), registry=make_test_registry())
    response = app.test_client().get(
        f"/owns?collectionId=bayc&wallet={VALID_WALLET}&tokenId=1234"
    )
    data = response.get_json()

    assert response.status_code == 400
    assert data["ok"] is False
    assert data["votingPower"] == 0
    assert data["error"] == "invalid_collection_id"


def test_invalid_wallet_still_returns_zero_voting_power_json() -> None:
    app = create_app(checker=FakeChecker(), registry=make_test_registry())
    response = app.test_client().get("/owns?collectionId=1&wallet=bad&tokenId=1234")
    data = response.get_json()

    assert response.status_code == 200
    assert data["ok"] is False
    assert data["owns"] is False
    assert data["ownsInt"] == 0
    assert data["votingPower"] == 0
    assert data["error"] == "invalid_wallet"


def test_invalid_token_id_still_returns_zero_voting_power_json() -> None:
    app = create_app(checker=FakeChecker(), registry=make_test_registry())
    response = app.test_client().get(
        f"/owns?collectionId=1&wallet={VALID_WALLET}&tokenId=-1"
    )
    data = response.get_json()

    assert response.status_code == 200
    assert data["ok"] is False
    assert data["owns"] is False
    assert data["ownsInt"] == 0
    assert data["votingPower"] == 0
    assert data["error"] == "invalid_token_id"


def test_owner_of_revert_still_returns_zero_voting_power_json() -> None:
    app = create_app(
        checker=FakeChecker(should_raise=True), registry=make_test_registry()
    )
    response = app.test_client().get(
        f"/owns?collectionId=1&wallet={VALID_WALLET}&tokenId=1234"
    )
    data = response.get_json()

    assert response.status_code == 200
    assert data["ok"] is False
    assert data["owns"] is False
    assert data["ownsInt"] == 0
    assert data["votingPower"] == 0
    assert data["error"] == "ownerOf_reverted"


def test_registry_response_decodes_owner_comparison_case_insensitively() -> None:
    app = create_app(
        checker=FakeChecker(owner=OWNER.upper()), registry=make_test_registry()
    )
    response = app.test_client().get(
        f"/owns?collectionId=1&wallet={VALID_WALLET.lower()}&tokenId=1234"
    )
    data = response.get_json()

    assert response.status_code == 200
    assert data["owns"] is True
    assert data["votingPower"] == 1


def make_test_registry() -> CollectionRegistry:
    return CollectionRegistry(
        collections={
            1: CollectionConfig(
                collection_id=1,
                short_label="quills",
                target_collection_label="quills-adventure",
                target_chain_label="somnia-mainnet",
                target_nft_contract=QUILLS_CONTRACT,
                target_rpc_url="https://quills.invalid",
                voting_power=1,
            ),
            2: CollectionConfig(
                collection_id=2,
                short_label="bayc",
                target_collection_label="bored-ape-yacht-club",
                target_chain_label="ethereum-mainnet",
                target_nft_contract=BAYC_CONTRACT,
                target_rpc_url="https://bayc.invalid",
                voting_power=2,
            ),
        }
    )
