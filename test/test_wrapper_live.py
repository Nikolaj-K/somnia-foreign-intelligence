"""
What: Env-gated live smoke test for the ownership wrapper.
Run:
  QUILLS_RPC_URL=... BAYC_RPC_URL=... LIVE_TEST_WALLET=... LIVE_TEST_TOKEN_ID=... \
    python -m pytest test/test_wrapper_live.py

This test is skipped unless all required environment variables are present. It
uses Flask's test client with the real wrapper checker, so it performs live
read-only RPC calls but does not spend funds or use private keys.
"""

from __future__ import annotations

import os

import pytest

from wrapper.app import create_app


REQUIRED_ENV = [
    "LIVE_TEST_WALLET",
    "LIVE_TEST_TOKEN_ID",
]


def test_live_wrapper_owns_response_shape() -> None:
    missing = [key for key in REQUIRED_ENV if not os.environ.get(key)]
    if missing:
        pytest.skip("missing live wrapper env: " + ", ".join(missing))

    app = create_app()
    wallet = os.environ["LIVE_TEST_WALLET"]
    token_id = os.environ["LIVE_TEST_TOKEN_ID"]
    collection_id = os.environ.get("LIVE_TEST_COLLECTION_ID", "1")
    response = app.test_client().get(
        f"/owns?collectionId={collection_id}&wallet={wallet}&tokenId={token_id}"
    )
    data = response.get_json()

    assert response.status_code == 200
    assert response.headers["Cache-Control"] == "no-store"
    assert set(data) >= {
        "ok",
        "owns",
        "ownsInt",
        "votingPower",
        "collectionId",
        "collection",
        "wallet",
        "owner",
        "tokenId",
        "checkedBlock",
        "targetChain",
        "targetCollection",
    }
    assert isinstance(data["ok"], bool)
    assert isinstance(data["owns"], bool)
    assert data["ownsInt"] in (0, 1)
    assert data["ownsInt"] == (1 if data["owns"] else 0)
    assert data["votingPower"] >= 0
    assert data["tokenId"] == str(token_id)

    expected_owns = os.environ.get("LIVE_TEST_EXPECTED_OWNS")
    if expected_owns is not None:
        assert data["owns"] is (expected_owns.lower() == "true")

    expected_owner = os.environ.get("LIVE_TEST_EXPECTED_OWNER")
    if expected_owner is not None:
        assert data["owner"].lower() == expected_owner.lower()
