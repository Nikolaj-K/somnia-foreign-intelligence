"""
What: Read-only smoke check for a deployed ownership wrapper URL.
Run:
  python scripts/check_public_wrapper.py \
    --base-url https://YOUR_CLOUD_RUN_SERVICE/owns \
    --collection-id 1 \
    --wallet <DEMO_WALLET_ADDRESS> \
    --token-id <TOKEN_ID>
Deps: repo requirements, including Rich for logging.

This script never uses a private key. It checks that the public wrapper returns
JSON with human-readable ownership fields and the live-agent `votingPower`
field expected by the documented Somnia fetchUint path.
"""

from __future__ import annotations

import argparse
import json
import logging
import re
import urllib.parse
import urllib.request
from typing import Any

from rich.logging import RichHandler


LOGGER = logging.getLogger("public-wrapper-check")
WALLET_PATTERN = re.compile(r"^0x[a-fA-F0-9]{40}$")


def main() -> None:
    args = parse_args()
    configure_logging()
    assert args.base_url.startswith(("http://", "https://")), "base URL must be HTTP(S)"
    assert "?" not in args.base_url, "base URL must not include a query string"
    assert args.collection_id >= 1, "collection ID must be positive"
    assert WALLET_PATTERN.match(args.wallet), "wallet must be an EVM address"
    assert args.token_id >= 0, "token ID must be non-negative"

    positive = fetch_owns(args.base_url, args.collection_id, args.wallet, args.token_id)
    assert_common_shape(positive)
    if args.expected_owns is not None:
        assert positive["owns"] is args.expected_owns, "positive owns mismatch"
        assert positive["ownsInt"] == (
            1 if args.expected_owns else 0
        ), "positive ownsInt mismatch"
    LOGGER.info("positive_response=%s", json.dumps(positive, sort_keys=True))

    if args.negative_wallet:
        assert WALLET_PATTERN.match(
            args.negative_wallet
        ), "negative wallet must be an EVM address"
        negative = fetch_owns(
            args.base_url,
            args.collection_id,
            args.negative_wallet,
            args.token_id,
        )
        assert_common_shape(negative)
        assert negative["owns"] is False, "negative owns should be false"
        assert negative["ownsInt"] == 0, "negative ownsInt should be 0"
        LOGGER.info("negative_response=%s", json.dumps(negative, sort_keys=True))


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Check public ownership wrapper")
    parser.add_argument("--base-url", required=True, help="Public URL ending in /owns")
    parser.add_argument("--collection-id", type=int, default=1)
    parser.add_argument("--wallet", required=True)
    parser.add_argument("--token-id", required=True, type=int)
    parser.add_argument(
        "--expected-owns",
        choices=["true", "false"],
        default=None,
        help="Optional expected positive owns value.",
    )
    parser.add_argument(
        "--negative-wallet",
        default="0x0000000000000000000000000000000000000000",
        help="Optional wallet expected not to own the token.",
    )
    args = parser.parse_args()
    if args.expected_owns is not None:
        args.expected_owns = args.expected_owns == "true"
    return args


def fetch_owns(
    base_url: str,
    collection_id: int,
    wallet: str,
    token_id: int,
) -> dict[str, Any]:
    query = urllib.parse.urlencode(
        {
            "collectionId": str(collection_id),
            "wallet": wallet,
            "tokenId": str(token_id),
        }
    )
    url = f"{base_url}?{query}"
    LOGGER.info("fetching=%s", url)
    with urllib.request.urlopen(url, timeout=30) as response:
        assert response.status == 200, f"unexpected HTTP status: {response.status}"
        raw = response.read().decode("utf-8")
    data = json.loads(raw)
    assert isinstance(data, dict), "wrapper response must be a JSON object"
    return data


def assert_common_shape(data: dict[str, Any]) -> None:
    for key in (
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
    ):
        assert key in data, f"missing response key: {key}"
    assert isinstance(data["ok"], bool), "ok must be bool"
    assert isinstance(data["owns"], bool), "owns must be bool"
    assert data["ownsInt"] in (0, 1), "ownsInt must be 0 or 1"
    assert data["ownsInt"] == (1 if data["owns"] else 0), "owns/ownsInt disagree"
    assert isinstance(data["votingPower"], int), "votingPower must be int"
    assert data["votingPower"] >= 0, "votingPower must be non-negative"
    assert data["votingPower"] == 0 or data["owns"], "votingPower implies owns"


def configure_logging() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(message)s",
        handlers=[RichHandler(rich_tracebacks=True, show_path=False)],
    )


if __name__ == "__main__":
    main()
