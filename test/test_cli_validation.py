"""
What: Unit tests for CLI-only validation helpers.
Run:  python -m pytest test/test_cli_validation.py
"""

from __future__ import annotations

import pytest

from scripts.somnia_vote_cli import assert_vote_contract_balance_sufficient
from scripts.somnia_vote_cli import assert_valid_base_ownership_url
from scripts.somnia_vote_cli import assert_live_agent_settings
from scripts.somnia_vote_cli import build_vote_balance_status
from scripts.somnia_vote_cli import build_vote_next_checks_block
from scripts.somnia_vote_cli import DEFAULT_JSON_API_AGENT_ID
from scripts.somnia_vote_cli import DEFAULT_JSON_API_FETCH_UINT_SELECTOR
from scripts.somnia_vote_cli import DEFAULT_COLLECTIONS
from scripts.somnia_vote_cli import OWNERSHIP_UINT_SELECTOR
from scripts.somnia_vote_cli import require_response_kind
from scripts.somnia_vote_cli import resolve_collection_id


@pytest.mark.parametrize(
    "url",
    [
        "https://wrapper.example/owns",
        "http://127.0.0.1:8080/owns",
    ],
)
def test_accepts_valid_base_ownership_url(url: str) -> None:
    assert_valid_base_ownership_url(url)


@pytest.mark.parametrize(
    "url",
    [
        "",
        "wrapper.example/owns",
        "ftp://wrapper.example/owns",
        "https://wrapper.example/owns?wallet=already",
    ],
)
def test_rejects_invalid_base_ownership_url(url: str) -> None:
    with pytest.raises(AssertionError):
        assert_valid_base_ownership_url(url)


def test_live_agent_settings_accept_documented_uint_mode() -> None:
    assert_live_agent_settings(
        json_api_agent_id=DEFAULT_JSON_API_AGENT_ID,
        json_api_method_selector=DEFAULT_JSON_API_FETCH_UINT_SELECTOR,
        ownership_response_kind="uint",
        base_ownership_url="https://public.invalid/owns",
        agent_price_per_validator_wei=1,
    )


def test_live_agent_settings_reject_bool_mode() -> None:
    with pytest.raises(AssertionError, match="bool live mode"):
        assert_live_agent_settings(
            json_api_agent_id=DEFAULT_JSON_API_AGENT_ID,
            json_api_method_selector="0x5cd80388",
            ownership_response_kind="bool",
            base_ownership_url="https://public.invalid/owns",
            agent_price_per_validator_wei=1,
        )


def test_response_kind_validation() -> None:
    assert require_response_kind("UINT") == "uint"
    with pytest.raises(AssertionError):
        require_response_kind("number")


def test_vote_next_checks_block_uses_explicit_contract_and_request_variables() -> None:
    block = build_vote_next_checks_block(
        config_path="config.local.json",
        contract_address="0x535A56B754e705ab251cD89C4Aa43e62c5F27B3F",
        request_id=2278035,
        collection_id=2,
        token_id=1234,
        choice=2,
    )

    assert block == "\n".join(
        [
            "next checks:",
            'VOTE_CONTRACT_ADDRESS="0x535A56B754e705ab251cD89C4Aa43e62c5F27B3F"',
            'REQUEST_ID="2278035"',
            "",
            "python scripts/somnia_vote_cli.py --config config.local.json pending \\",
            '  --contract-address "$VOTE_CONTRACT_ADDRESS" \\',
            '  --request-id "$REQUEST_ID"',
            "",
            "python scripts/somnia_vote_cli.py --config config.local.json read \\",
            '  --contract-address "$VOTE_CONTRACT_ADDRESS" \\',
            "  --collection-id 2 \\",
            "  --token-id 1234",
            "",
            "python scripts/somnia_vote_cli.py --config config.local.json count \\",
            '  --contract-address "$VOTE_CONTRACT_ADDRESS" \\',
            "  --choice 2",
            "",
            "pending exists=True means the callback has not completed yet.",
            "pending exists=False means the request has been cleared.",
            "If has_voted=True, the vote was accepted and counted.",
            (
                "If has_voted=False after pending is cleared, the ownership check "
                "failed or the callback did not record the vote."
            ),
        ]
    )


def test_vote_balance_status_reports_sufficiency_and_remaining_requests() -> None:
    status = build_vote_balance_status(
        contract_balance_wei=500,
        request_value_wei=120,
        reward_wei=80,
    )

    assert status["balance_sufficient"] is True
    assert status["balance_warn_for_successful_vote"] is False
    assert status["estimated_remaining_requests"] == 4
    assert status["estimated_successful_votes"] == 2


def test_vote_balance_status_handles_zero_request_value() -> None:
    status = build_vote_balance_status(
        contract_balance_wei=0,
        request_value_wei=0,
        reward_wei=0,
    )

    assert status["balance_sufficient"] is True
    assert status["estimated_remaining_requests"] is None
    assert status["estimated_successful_votes"] is None


def test_vote_balance_status_warns_when_reward_may_not_be_covered() -> None:
    status = build_vote_balance_status(
        contract_balance_wei=150,
        request_value_wei=120,
        reward_wei=80,
    )

    assert status["balance_sufficient"] is True
    assert status["balance_warn_for_successful_vote"] is True
    assert status["accepted_vote_cost_wei"] == 200


def test_uint_selector_path_is_voting_power() -> None:
    assert OWNERSHIP_UINT_SELECTOR == "votingPower"


def test_collections_command_metadata_contains_quills_and_bayc() -> None:
    assert DEFAULT_COLLECTIONS[1]["label"] == "quills-adventure"
    assert DEFAULT_COLLECTIONS[1]["chain"] == "somnia-mainnet"
    assert DEFAULT_COLLECTIONS[1]["voting_power"] == 1
    assert DEFAULT_COLLECTIONS[2]["label"] == "bored-ape-yacht-club"
    assert DEFAULT_COLLECTIONS[2]["chain"] == "ethereum-mainnet"
    assert DEFAULT_COLLECTIONS[2]["voting_power"] == 2


def test_collection_alias_resolution() -> None:
    class Args:
        collection_id = None
        collection = "bayc"

    assert resolve_collection_id(Args()) == 2


def test_collection_id_resolution_rejects_out_of_uint8_range() -> None:
    class Args:
        collection_id = 999
        collection = None

    with pytest.raises(AssertionError, match="uint8"):
        resolve_collection_id(Args())


class _FakeEth:
    def get_balance(self, address: str) -> int:
        assert address == "0x1111111111111111111111111111111111111111"
        return 50


class _FakeWeb3:
    eth = _FakeEth()


class _FakeNetwork:
    native_symbol = "STT"


class _FakeConfig:
    network = _FakeNetwork()


class _FakeContract:
    address = "0x1111111111111111111111111111111111111111"


def test_vote_balance_preflight_fails_before_sending_when_underfunded() -> None:
    with pytest.raises(AssertionError, match="vote\\(\\) is not payable"):
        assert_vote_contract_balance_sufficient(
            web3=_FakeWeb3(),
            config=_FakeConfig(),
            contract=_FakeContract(),
            request_value_wei=120,
            config_path="config.local.json",
        )
