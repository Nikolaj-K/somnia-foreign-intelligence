"""
What: Local contract tests for NftGatedVote using eth-tester.
Run:  python -m pytest test/test_nft_gated_vote.py
Deps: Python test deps from requirements.txt.

These tests intentionally avoid Somnia RPC and the live JSON API agent. They use
MockSomniaAgentPlatform to exercise the async request/callback path locally.
"""

from __future__ import annotations

from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest
from web3 import EthereumTesterProvider
from web3 import Web3
from web3.contract import Contract
from web3.logs import DISCARD

from scripts.solidity_build import compile_project_contracts
from scripts.solidity_build import resolve_solc_binary


PROJECT_ROOT = Path(__file__).resolve().parent.parent
SOLC_BINARY = resolve_solc_binary(PROJECT_ROOT)
BASE_URL = "https://wrapper.example/owns"
JSON_API_AGENT_ID = 123
JSON_API_METHOD_SELECTOR = "0x3bbc1302"
OWNERSHIP_RESPONSE_KIND_UINT = 1
REWARD_WEI = Web3.to_wei(Decimal("0.01"), "ether")
MAX_CHOICE = 3
QUILLS_COLLECTION_ID = 1
BAYC_COLLECTION_ID = 2


@pytest.fixture(scope="session")
def compiled_contracts() -> dict[str, Any]:
    assert SOLC_BINARY.exists(), f"Missing solc binary: {SOLC_BINARY}"
    return compile_project_contracts(PROJECT_ROOT, SOLC_BINARY)


@pytest.fixture()
def web3() -> Web3:
    provider = EthereumTesterProvider()
    web3 = Web3(provider)
    web3.eth.default_account = web3.eth.accounts[0]
    return web3


@pytest.fixture()
def contracts(web3: Web3, compiled_contracts: dict[str, Any]) -> dict[str, Contract]:
    mock_platform = deploy_contract(
        web3,
        compiled_contracts,
        "contracts/test/MockSomniaAgentPlatform.sol",
        "MockSomniaAgentPlatform",
        [0],
    )
    vote = deploy_contract(
        web3,
        compiled_contracts,
        "contracts/NftGatedVote.sol",
        "NftGatedVote",
        [
            mock_platform.address,
            JSON_API_AGENT_ID,
            JSON_API_METHOD_SELECTOR,
            0,
            3,
            BASE_URL,
            OWNERSHIP_RESPONSE_KIND_UINT,
            REWARD_WEI,
            MAX_CHOICE,
        ],
    )
    return {"mock_platform": mock_platform, "vote": vote}


def test_accepts_vote_after_true_callback(
    web3: Web3,
    contracts: dict[str, Contract],
) -> None:
    vote = contracts["vote"]
    mock_platform = contracts["mock_platform"]
    voter = web3.eth.accounts[1]
    token_id = 1001

    fund_contract(web3, vote.address, Web3.to_wei(Decimal("0.1"), "ether"))
    request_id = request_vote(web3, vote, voter, token_id, 2)

    pending = vote.functions.pendingVotes(request_id).call()
    assert pending[0] is True
    assert pending[1] == voter
    assert pending[2] == QUILLS_COLLECTION_ID
    assert pending[3] == token_id
    assert pending[4] == 2

    before_contract_balance = web3.eth.get_balance(vote.address)
    tx_hash = mock_platform.functions.fulfillBool(request_id, True).transact(
        {"from": web3.eth.accounts[0]}
    )
    web3.eth.wait_for_transaction_receipt(tx_hash)

    assert vote.functions.getTokenVote(token_id).call() == 2
    assert vote.functions.voteCounts(2).call() == 1
    assert vote.functions.tokenVoter(token_id).call() == voter
    assert vote.functions.pendingVotes(request_id).call()[0] is False
    assert web3.eth.get_balance(vote.address) == before_contract_balance - REWARD_WEI


def test_rejects_vote_when_ownership_check_is_false(
    web3: Web3,
    contracts: dict[str, Contract],
) -> None:
    vote = contracts["vote"]
    mock_platform = contracts["mock_platform"]
    token_id = 1002
    request_id = request_vote(web3, vote, web3.eth.accounts[1], token_id, 1)

    tx_hash = mock_platform.functions.fulfillBool(request_id, False).transact(
        {"from": web3.eth.accounts[0]}
    )
    web3.eth.wait_for_transaction_receipt(tx_hash)

    assert vote.functions.getTokenVote(token_id).call() == 0
    assert vote.functions.voteCounts(1).call() == 0
    assert vote.functions.pendingVotes(request_id).call()[0] is False


def test_token_pending_lock_blocks_duplicate_request_until_callback(
    web3: Web3,
    contracts: dict[str, Contract],
) -> None:
    vote = contracts["vote"]
    mock_platform = contracts["mock_platform"]
    token_id = 42
    fund_contract(web3, vote.address, Web3.to_wei(Decimal("0.1"), "ether"))

    first_request_id = request_vote(web3, vote, web3.eth.accounts[1], token_id, 1)
    assert vote.functions.tokenPendingRequest(token_id).call() == first_request_id

    with pytest.raises(Exception, match="token request pending"):
        vote.functions.vote(QUILLS_COLLECTION_ID, token_id, 2).transact(
            {"from": web3.eth.accounts[2]}
        )

    tx_hash = mock_platform.functions.fulfillBool(first_request_id, True).transact(
        {"from": web3.eth.accounts[0]}
    )
    web3.eth.wait_for_transaction_receipt(tx_hash)

    assert vote.functions.getTokenVote(token_id).call() == 1
    assert vote.functions.tokenVoter(token_id).call() == web3.eth.accounts[1]
    assert vote.functions.voteCounts(1).call() == 1
    assert vote.functions.tokenPendingRequest(token_id).call() == 0
    assert vote.functions.pendingVotes(first_request_id).call()[0] is False


def test_quills_and_bayc_vote_keys_do_not_collide_for_same_token_id(
    contracts: dict[str, Contract],
) -> None:
    vote = contracts["vote"]
    token_id = 777

    assert vote.functions.voteKeyFor(QUILLS_COLLECTION_ID, token_id).call() != (
        vote.functions.voteKeyFor(BAYC_COLLECTION_ID, token_id).call()
    )


def test_bayc_voting_power_two_increments_weighted_count_by_two(
    web3: Web3,
    contracts: dict[str, Contract],
) -> None:
    vote = contracts["vote"]
    mock_platform = contracts["mock_platform"]
    token_id = 2001
    request_id = request_vote(
        web3,
        vote,
        web3.eth.accounts[1],
        token_id,
        3,
        collection_id=BAYC_COLLECTION_ID,
    )

    pending = vote.functions.pendingVotes(request_id).call()
    assert pending[2] == BAYC_COLLECTION_ID
    fulfill_vote(web3, mock_platform, request_id, 2)

    assert vote.functions.hasTokenVoted(BAYC_COLLECTION_ID, token_id).call() is True
    assert vote.functions.getTokenVote(BAYC_COLLECTION_ID, token_id).call() == 3
    assert vote.functions.tokenVotingPower(BAYC_COLLECTION_ID, token_id).call() == 2
    assert vote.functions.voteCounts(3).call() == 2


def test_zero_voting_power_rejects_and_does_not_record(
    web3: Web3,
    contracts: dict[str, Contract],
) -> None:
    vote = contracts["vote"]
    mock_platform = contracts["mock_platform"]
    token_id = 2002
    request_id = request_vote(
        web3,
        vote,
        web3.eth.accounts[1],
        token_id,
        1,
        collection_id=BAYC_COLLECTION_ID,
    )

    fulfill_vote(web3, mock_platform, request_id, 0)

    assert vote.functions.hasTokenVoted(BAYC_COLLECTION_ID, token_id).call() is False
    assert vote.functions.voteCounts(1).call() == 0


def test_same_token_id_across_collections_can_vote_independently(
    web3: Web3,
    contracts: dict[str, Contract],
) -> None:
    vote = contracts["vote"]
    mock_platform = contracts["mock_platform"]
    token_id = 2003

    quills_request_id = request_vote(
        web3,
        vote,
        web3.eth.accounts[1],
        token_id,
        1,
        collection_id=QUILLS_COLLECTION_ID,
    )
    bayc_request_id = request_vote(
        web3,
        vote,
        web3.eth.accounts[2],
        token_id,
        2,
        collection_id=BAYC_COLLECTION_ID,
    )

    fulfill_vote(web3, mock_platform, quills_request_id, 1)
    fulfill_vote(web3, mock_platform, bayc_request_id, 2)

    assert vote.functions.getTokenVote(QUILLS_COLLECTION_ID, token_id).call() == 1
    assert vote.functions.getTokenVote(BAYC_COLLECTION_ID, token_id).call() == 2
    assert vote.functions.getAllChoiceCounts().call() == [1, 2, 0]


def test_double_vote_for_same_collection_and_token_is_prevented(
    web3: Web3,
    contracts: dict[str, Contract],
) -> None:
    vote = contracts["vote"]
    mock_platform = contracts["mock_platform"]
    token_id = 2004
    request_id = request_vote(
        web3,
        vote,
        web3.eth.accounts[1],
        token_id,
        1,
        collection_id=BAYC_COLLECTION_ID,
    )
    fulfill_vote(web3, mock_platform, request_id, 2)

    with pytest.raises(Exception, match="token already voted"):
        vote.functions.vote(BAYC_COLLECTION_ID, token_id, 2).transact(
            {"from": web3.eth.accounts[2]}
        )


def test_unsupported_collection_rejected_before_request(
    web3: Web3,
    contracts: dict[str, Contract],
) -> None:
    vote = contracts["vote"]

    with pytest.raises(Exception, match="unsupported collection"):
        vote.functions.vote(99, 1, 1).transact({"from": web3.eth.accounts[1]})


def test_choice_count_helpers_and_leader_unique_winner(
    web3: Web3,
    contracts: dict[str, Contract],
) -> None:
    vote = contracts["vote"]
    mock_platform = contracts["mock_platform"]

    first_request_id = request_vote(web3, vote, web3.eth.accounts[1], 1101, 1)
    second_request_id = request_vote(web3, vote, web3.eth.accounts[2], 1102, 1)
    third_request_id = request_vote(web3, vote, web3.eth.accounts[3], 1103, 2)

    fulfill_vote(web3, mock_platform, first_request_id, True)
    fulfill_vote(web3, mock_platform, second_request_id, True)
    fulfill_vote(web3, mock_platform, third_request_id, True)

    assert vote.functions.getAllChoiceCounts().call() == [2, 1, 0]
    leader = vote.functions.leadingChoice().call()
    assert leader[0] == 1
    assert leader[1] == 2
    assert leader[2] is True
    assert leader[3] is False


def test_leading_choice_reports_tie(
    web3: Web3,
    contracts: dict[str, Contract],
) -> None:
    vote = contracts["vote"]
    mock_platform = contracts["mock_platform"]

    first_request_id = request_vote(web3, vote, web3.eth.accounts[1], 1201, 1)
    second_request_id = request_vote(web3, vote, web3.eth.accounts[2], 1202, 2)

    fulfill_vote(web3, mock_platform, first_request_id, True)
    fulfill_vote(web3, mock_platform, second_request_id, True)

    assert vote.functions.getAllChoiceCounts().call() == [1, 1, 0]
    leader = vote.functions.leadingChoice().call()
    assert leader[2] is True
    assert leader[3] is True


def test_leading_choice_uses_weighted_counts(
    web3: Web3,
    contracts: dict[str, Contract],
) -> None:
    vote = contracts["vote"]
    mock_platform = contracts["mock_platform"]

    quills_request_id = request_vote(
        web3,
        vote,
        web3.eth.accounts[1],
        2201,
        1,
        collection_id=QUILLS_COLLECTION_ID,
    )
    bayc_request_id = request_vote(
        web3,
        vote,
        web3.eth.accounts[2],
        2201,
        2,
        collection_id=BAYC_COLLECTION_ID,
    )

    fulfill_vote(web3, mock_platform, quills_request_id, 1)
    fulfill_vote(web3, mock_platform, bayc_request_id, 2)

    leader = vote.functions.leadingChoice().call()
    assert leader[0] == 2
    assert leader[1] == 2
    assert leader[2] is True
    assert leader[3] is False


def test_rejects_invalid_choices(web3: Web3, contracts: dict[str, Contract]) -> None:
    vote = contracts["vote"]
    voter = web3.eth.accounts[1]

    with pytest.raises(Exception, match="choice zero"):
        vote.functions.vote(QUILLS_COLLECTION_ID, 1, 0).transact({"from": voter})

    with pytest.raises(Exception, match="choice too high"):
        vote.functions.vote(QUILLS_COLLECTION_ID, 1, MAX_CHOICE + 1).transact(
            {"from": voter}
        )


def test_poll_metadata_exposes_ai_assistant_theme(
    contracts: dict[str, Contract],
) -> None:
    vote = contracts["vote"]

    assert (
        vote.functions.pollQuestion().call()
        == "Which AI assistant should lead the next agentic workflow?"
    )
    assert vote.functions.choiceLabel(1).call() == "ChatGPT"
    assert vote.functions.choiceLabel(2).call() == "Claude"
    assert vote.functions.choiceLabel(3).call() == "DeepSeek"
    assert vote.functions.maxChoice().call() == MAX_CHOICE


def test_collection_metadata_exposes_supported_weighted_gates(
    contracts: dict[str, Contract],
) -> None:
    vote = contracts["vote"]

    assert vote.functions.maxCollectionId().call() == 2
    assert vote.functions.supportedCollectionIds().call() == [
        QUILLS_COLLECTION_ID,
        BAYC_COLLECTION_ID,
    ]
    assert vote.functions.isSupportedCollection(QUILLS_COLLECTION_ID).call() is True
    assert vote.functions.isSupportedCollection(BAYC_COLLECTION_ID).call() is True
    assert vote.functions.isSupportedCollection(99).call() is False
    assert vote.functions.collectionLabel(QUILLS_COLLECTION_ID).call() == (
        "quills-adventure"
    )
    assert vote.functions.collectionChainLabel(QUILLS_COLLECTION_ID).call() == (
        "somnia-mainnet"
    )
    assert vote.functions.collectionVotingPower(QUILLS_COLLECTION_ID).call() == 1
    assert vote.functions.collectionLabel(BAYC_COLLECTION_ID).call() == (
        "bored-ape-yacht-club"
    )
    assert vote.functions.collectionChainLabel(BAYC_COLLECTION_ID).call() == (
        "ethereum-mainnet"
    )
    assert vote.functions.collectionVotingPower(BAYC_COLLECTION_ID).call() == 2


def test_choice_count_helpers_and_leader_no_votes(
    contracts: dict[str, Contract],
) -> None:
    vote = contracts["vote"]

    assert vote.functions.getChoiceCount(1).call() == 0
    assert vote.functions.getAllChoiceCounts().call() == [0, 0, 0]
    leader = vote.functions.leadingChoice().call()
    assert leader[0] == 0
    assert leader[1] == 0
    assert leader[2] is False
    assert leader[3] is False


@pytest.mark.parametrize(
    "bad_base_url",
    [
        "",
        "ftp://wrapper.example/owns",
        "wrapper.example/owns",
        "https://wrapper.example/owns?already=bad",
    ],
)
def test_constructor_rejects_invalid_base_ownership_url(
    web3: Web3,
    compiled_contracts: dict[str, Any],
    contracts: dict[str, Contract],
    bad_base_url: str,
) -> None:
    mock_platform = contracts["mock_platform"]
    with pytest.raises(Exception, match="invalid base ownership url"):
        deploy_contract(
            web3,
            compiled_contracts,
            "contracts/NftGatedVote.sol",
            "NftGatedVote",
            [
                mock_platform.address,
                JSON_API_AGENT_ID,
                JSON_API_METHOD_SELECTOR,
                0,
                3,
                bad_base_url,
                OWNERSHIP_RESPONSE_KIND_UINT,
                REWARD_WEI,
                MAX_CHOICE,
            ],
        )


def test_set_base_ownership_url_validates_url(
    web3: Web3,
    contracts: dict[str, Contract],
) -> None:
    vote = contracts["vote"]
    assert vote.functions.isValidBaseOwnershipUrl("https://good.example/owns").call()
    assert not vote.functions.isValidBaseOwnershipUrl(
        "https://bad.example/owns?x=1"
    ).call()

    with pytest.raises(Exception, match="invalid base ownership url"):
        vote.functions.setBaseOwnershipUrl("https://bad.example/owns?x=1").transact(
            {"from": web3.eth.accounts[0]}
        )

    tx_hash = vote.functions.setBaseOwnershipUrl("https://good.example/owns").transact(
        {"from": web3.eth.accounts[0]}
    )
    web3.eth.wait_for_transaction_receipt(tx_hash)
    assert vote.functions.baseOwnershipUrl().call() == "https://good.example/owns"


def test_ownership_url_and_payload_use_collection_id_and_voting_power_selector(
    web3: Web3,
    contracts: dict[str, Contract],
) -> None:
    vote = contracts["vote"]
    wallet = web3.eth.accounts[1]
    token_id = 901

    url = vote.functions.ownershipUrl(BAYC_COLLECTION_ID, wallet, token_id).call()

    assert url == (
        f"{BASE_URL}?collectionId=2&wallet={wallet.lower()}&tokenId={token_id}"
    )
    assert vote.functions.ownershipSelectorPath().call() == "votingPower"
    payload = vote.functions.jsonApiPayload(
        BAYC_COLLECTION_ID,
        wallet,
        token_id,
    ).call()
    assert b"votingPower" in payload


def test_vote_records_even_when_reward_balance_is_missing(
    web3: Web3,
    contracts: dict[str, Contract],
) -> None:
    vote = contracts["vote"]
    mock_platform = contracts["mock_platform"]
    token_id = 99
    request_id = request_vote(web3, vote, web3.eth.accounts[1], token_id, 3)

    tx_hash = mock_platform.functions.fulfillBool(request_id, True).transact(
        {"from": web3.eth.accounts[0]}
    )
    web3.eth.wait_for_transaction_receipt(tx_hash)

    assert vote.functions.getTokenVote(token_id).call() == 3
    assert vote.functions.voteCounts(3).call() == 1
    assert web3.eth.get_balance(vote.address) == 0


def test_rejects_unauthorized_direct_callback(
    web3: Web3,
    contracts: dict[str, Contract],
) -> None:
    vote = contracts["vote"]
    request_id = request_vote(web3, vote, web3.eth.accounts[1], 123, 1)
    callback_selector = vote.functions.handleResponseSelector().call()
    empty_request = (
        request_id,
        web3.eth.accounts[1],
        vote.address,
        callback_selector,
        [],
        [],
        0,
        0,
        1,
        0,
        0,
        2,
        0,
        0,
        0,
    )

    with pytest.raises(Exception, match="only platform"):
        vote.functions.handleResponse(request_id, [], 2, empty_request).transact(
            {"from": web3.eth.accounts[1]}
        )


def test_second_callback_for_deleted_pending_vote_is_rejected(
    web3: Web3,
    contracts: dict[str, Contract],
) -> None:
    vote = contracts["vote"]
    mock_platform = contracts["mock_platform"]
    request_id = request_vote(web3, vote, web3.eth.accounts[1], 321, 1)

    tx_hash = mock_platform.functions.fulfillBool(request_id, True).transact(
        {"from": web3.eth.accounts[0]}
    )
    web3.eth.wait_for_transaction_receipt(tx_hash)
    tx_hash = mock_platform.functions.fulfillBool(request_id, True).transact(
        {"from": web3.eth.accounts[0]}
    )
    receipt = web3.eth.wait_for_transaction_receipt(tx_hash)

    rejected_events = vote.events.VoteRejected().process_receipt(
        receipt,
        errors=DISCARD,
    )
    assert len(rejected_events) == 1
    assert rejected_events[0]["args"]["reason"] == "missing_pending_vote"


def test_malformed_success_bytes_do_not_record_vote(
    web3: Web3,
    contracts: dict[str, Contract],
) -> None:
    vote = contracts["vote"]
    mock_platform = contracts["mock_platform"]
    token_id = 444
    request_id = request_vote(web3, vote, web3.eth.accounts[1], token_id, 1)

    tx_hash = mock_platform.functions.fulfillRawSuccess(request_id, b"\x01").transact(
        {"from": web3.eth.accounts[0]}
    )
    receipt = web3.eth.wait_for_transaction_receipt(tx_hash)

    assert vote.functions.getTokenVote(token_id).call() == 0
    assert vote.functions.pendingVotes(request_id).call()[0] is False
    rejected_events = vote.events.VoteRejected().process_receipt(
        receipt,
        errors=DISCARD,
    )
    assert rejected_events[0]["args"]["reason"] == "no_success_ownership_response"


def test_uint_response_above_one_records_weighted_vote(
    web3: Web3,
    contracts: dict[str, Contract],
) -> None:
    vote = contracts["vote"]
    mock_platform = contracts["mock_platform"]
    token_id = 445
    request_id = request_vote(web3, vote, web3.eth.accounts[1], token_id, 1)

    tx_hash = mock_platform.functions.fulfillUint(request_id, 2).transact(
        {"from": web3.eth.accounts[0]}
    )
    receipt = web3.eth.wait_for_transaction_receipt(tx_hash)

    assert vote.functions.getTokenVote(token_id).call() == 1
    assert vote.functions.tokenPendingRequest(token_id).call() == 0
    recorded_events = vote.events.VoteRecorded().process_receipt(
        receipt,
        errors=DISCARD,
    )
    assert recorded_events[0]["args"]["votingPower"] == 2
    assert vote.functions.voteCounts(1).call() == 2


def test_aggregate_failure_rejects_even_with_successful_bool_response(
    web3: Web3,
    contracts: dict[str, Contract],
) -> None:
    vote = contracts["vote"]
    mock_platform = contracts["mock_platform"]
    token_id = 555
    request_id = request_vote(web3, vote, web3.eth.accounts[1], token_id, 1)

    tx_hash = mock_platform.functions.fulfillBoolWithStatus(
        request_id,
        True,
        3,
    ).transact({"from": web3.eth.accounts[0]})
    receipt = web3.eth.wait_for_transaction_receipt(tx_hash)

    assert vote.functions.getTokenVote(token_id).call() == 0
    rejected_events = vote.events.VoteRejected().process_receipt(
        receipt,
        errors=DISCARD,
    )
    assert rejected_events[0]["args"]["reason"] == "agent_status_not_success"


def test_expired_pending_vote_can_be_released(
    web3: Web3,
    contracts: dict[str, Contract],
) -> None:
    vote = contracts["vote"]
    token_id = 556
    request_id = request_vote(web3, vote, web3.eth.accounts[1], token_id, 1)
    assert vote.functions.tokenPendingRequest(token_id).call() == request_id

    tx_hash = vote.functions.setPendingRequestTimeoutSeconds(1).transact(
        {"from": web3.eth.accounts[0]}
    )
    web3.eth.wait_for_transaction_receipt(tx_hash)

    latest_block = web3.eth.get_block("latest")
    web3.provider.ethereum_tester.time_travel(latest_block["timestamp"] + 2)
    web3.provider.ethereum_tester.mine_blocks(1)

    tx_hash = vote.functions.releaseExpiredPendingVote(request_id).transact(
        {"from": web3.eth.accounts[2]}
    )
    receipt = web3.eth.wait_for_transaction_receipt(tx_hash)

    assert vote.functions.pendingVotes(request_id).call()[0] is False
    assert vote.functions.tokenPendingRequest(token_id).call() == 0
    rejected_events = vote.events.VoteRejected().process_receipt(
        receipt,
        errors=DISCARD,
    )
    assert rejected_events[0]["args"]["reason"] == "pending_vote_expired"

    retry_request_id = request_vote(web3, vote, web3.eth.accounts[2], token_id, 2)
    assert retry_request_id != request_id


def test_pause_and_unpause_control_vote_requests(
    web3: Web3,
    contracts: dict[str, Contract],
) -> None:
    vote = contracts["vote"]
    tx_hash = vote.functions.pause().transact({"from": web3.eth.accounts[0]})
    web3.eth.wait_for_transaction_receipt(tx_hash)

    with pytest.raises(Exception, match="paused"):
        vote.functions.vote(QUILLS_COLLECTION_ID, 1, 1).transact(
            {"from": web3.eth.accounts[1]}
        )

    tx_hash = vote.functions.unpause().transact({"from": web3.eth.accounts[0]})
    web3.eth.wait_for_transaction_receipt(tx_hash)
    request_id = request_vote(web3, vote, web3.eth.accounts[1], 1, 1)
    assert request_id == 1


def test_owner_can_update_agent_config(
    web3: Web3,
    contracts: dict[str, Contract],
) -> None:
    vote = contracts["vote"]
    new_selector = "0x12345678"
    tx_hash = vote.functions.setAgentConfig(
        999,
        new_selector,
        7,
        4,
        OWNERSHIP_RESPONSE_KIND_UINT,
    ).transact({"from": web3.eth.accounts[0]})
    web3.eth.wait_for_transaction_receipt(tx_hash)

    assert vote.functions.jsonApiAgentId().call() == 999
    assert vote.functions.jsonApiMethodSelector().call().hex() == "12345678"
    assert vote.functions.agentPricePerValidatorWei().call() == 7
    assert vote.functions.agentSubcommitteeSize().call() == 4
    assert vote.functions.ownershipResponseKind().call() == OWNERSHIP_RESPONSE_KIND_UINT

    with pytest.raises(Exception, match="only owner"):
        vote.functions.setAgentConfig(
            1,
            new_selector,
            1,
            1,
            OWNERSHIP_RESPONSE_KIND_UINT,
        ).transact({"from": web3.eth.accounts[1]})


def test_withdraw_is_owner_only(
    web3: Web3,
    contracts: dict[str, Contract],
) -> None:
    vote = contracts["vote"]
    amount_wei = Web3.to_wei(Decimal("0.02"), "ether")
    recipient = web3.eth.accounts[2]
    fund_contract(web3, vote.address, amount_wei)

    with pytest.raises(Exception, match="only owner"):
        vote.functions.withdraw(recipient, amount_wei).transact(
            {"from": web3.eth.accounts[1]}
        )

    before_recipient_balance = web3.eth.get_balance(recipient)
    tx_hash = vote.functions.withdraw(recipient, amount_wei).transact(
        {"from": web3.eth.accounts[0]}
    )
    web3.eth.wait_for_transaction_receipt(tx_hash)
    assert web3.eth.get_balance(recipient) == before_recipient_balance + amount_wei
    assert web3.eth.get_balance(vote.address) == 0


def test_debug_void_vote_decrements_count_and_clears_vote(
    web3: Web3,
    contracts: dict[str, Contract],
) -> None:
    vote = contracts["vote"]
    mock_platform = contracts["mock_platform"]
    token_id = 1301
    request_id = request_vote(web3, vote, web3.eth.accounts[1], token_id, 2)
    fulfill_vote(web3, mock_platform, request_id, True)

    tx_hash = vote.functions.debugOnlyVoidVote(token_id).transact(
        {"from": web3.eth.accounts[0]}
    )
    receipt = web3.eth.wait_for_transaction_receipt(tx_hash)

    assert vote.functions.getTokenVote(token_id).call() == 0
    assert vote.functions.tokenVoter(token_id).call() == Web3.to_checksum_address(
        "0x0000000000000000000000000000000000000000"
    )
    assert vote.functions.voteCounts(2).call() == 0
    events = vote.events.DebugVoteVoided().process_receipt(receipt, errors=DISCARD)
    assert events[0]["args"]["collectionId"] == QUILLS_COLLECTION_ID
    assert events[0]["args"]["tokenId"] == token_id
    assert events[0]["args"]["previousChoice"] == 2
    assert events[0]["args"]["previousWeight"] == 1


def test_debug_void_vote_reverts_for_non_voted_token(
    web3: Web3,
    contracts: dict[str, Contract],
) -> None:
    vote = contracts["vote"]

    with pytest.raises(Exception, match="token has not voted"):
        vote.functions.debugOnlyVoidVote(1302).transact({"from": web3.eth.accounts[0]})


def test_debug_void_vote_clears_only_selected_collection_token(
    web3: Web3,
    contracts: dict[str, Contract],
) -> None:
    vote = contracts["vote"]
    mock_platform = contracts["mock_platform"]
    token_id = 1304
    quills_request_id = request_vote(
        web3,
        vote,
        web3.eth.accounts[1],
        token_id,
        1,
        collection_id=QUILLS_COLLECTION_ID,
    )
    bayc_request_id = request_vote(
        web3,
        vote,
        web3.eth.accounts[2],
        token_id,
        1,
        collection_id=BAYC_COLLECTION_ID,
    )
    fulfill_vote(web3, mock_platform, quills_request_id, 1)
    fulfill_vote(web3, mock_platform, bayc_request_id, 2)
    assert vote.functions.voteCounts(1).call() == 3

    tx_hash = vote.functions.debugOnlyVoidVote(BAYC_COLLECTION_ID, token_id).transact(
        {"from": web3.eth.accounts[0]}
    )
    receipt = web3.eth.wait_for_transaction_receipt(tx_hash)

    assert vote.functions.hasTokenVoted(QUILLS_COLLECTION_ID, token_id).call() is True
    assert vote.functions.hasTokenVoted(BAYC_COLLECTION_ID, token_id).call() is False
    assert vote.functions.voteCounts(1).call() == 1
    events = vote.events.DebugVoteVoided().process_receipt(receipt, errors=DISCARD)
    assert events[0]["args"]["collectionId"] == BAYC_COLLECTION_ID
    assert events[0]["args"]["previousWeight"] == 2


def test_debug_cancel_pending_request_clears_and_later_callback_cannot_record(
    web3: Web3,
    contracts: dict[str, Contract],
) -> None:
    vote = contracts["vote"]
    mock_platform = contracts["mock_platform"]
    token_id = 1303
    request_id = request_vote(web3, vote, web3.eth.accounts[1], token_id, 1)

    tx_hash = vote.functions.debugOnlyCancelPendingRequest(request_id).transact(
        {"from": web3.eth.accounts[0]}
    )
    receipt = web3.eth.wait_for_transaction_receipt(tx_hash)

    assert vote.functions.pendingVotes(request_id).call()[0] is False
    assert vote.functions.tokenPendingRequest(token_id).call() == 0
    events = vote.events.DebugPendingRequestCancelled().process_receipt(
        receipt,
        errors=DISCARD,
    )
    assert events[0]["args"]["requestId"] == request_id

    fulfill_vote(web3, mock_platform, request_id, True)
    assert vote.functions.getTokenVote(token_id).call() == 0
    assert vote.functions.voteCounts(1).call() == 0


def test_debug_cancel_pending_request_unlocks_collection_specific_key(
    web3: Web3,
    contracts: dict[str, Contract],
) -> None:
    vote = contracts["vote"]
    token_id = 1305
    request_id = request_vote(
        web3,
        vote,
        web3.eth.accounts[1],
        token_id,
        1,
        collection_id=BAYC_COLLECTION_ID,
    )

    assert vote.functions.tokenPendingRequest(BAYC_COLLECTION_ID, token_id).call() == (
        request_id
    )
    assert (
        vote.functions.tokenPendingRequest(QUILLS_COLLECTION_ID, token_id).call() == 0
    )

    tx_hash = vote.functions.debugOnlyCancelPendingRequest(request_id).transact(
        {"from": web3.eth.accounts[0]}
    )
    receipt = web3.eth.wait_for_transaction_receipt(tx_hash)

    assert vote.functions.tokenPendingRequest(BAYC_COLLECTION_ID, token_id).call() == 0
    events = vote.events.DebugPendingRequestCancelled().process_receipt(
        receipt,
        errors=DISCARD,
    )
    assert events[0]["args"]["collectionId"] == BAYC_COLLECTION_ID

    retry_request_id = request_vote(
        web3,
        vote,
        web3.eth.accounts[2],
        token_id,
        2,
        collection_id=BAYC_COLLECTION_ID,
    )
    assert retry_request_id != request_id


def test_debug_withdraw_stt_transfers_balance_only_for_admin(
    web3: Web3,
    contracts: dict[str, Contract],
) -> None:
    vote = contracts["vote"]
    amount_wei = Web3.to_wei(Decimal("0.02"), "ether")
    recipient = web3.eth.accounts[2]
    fund_contract(web3, vote.address, amount_wei)

    with pytest.raises(Exception, match="only debug admin"):
        vote.functions.debugOnlyWithdrawSTT(recipient, amount_wei).transact(
            {"from": web3.eth.accounts[1]}
        )

    before_recipient_balance = web3.eth.get_balance(recipient)
    tx_hash = vote.functions.debugOnlyWithdrawSTT(recipient, amount_wei).transact(
        {"from": web3.eth.accounts[0]}
    )
    receipt = web3.eth.wait_for_transaction_receipt(tx_hash)

    assert web3.eth.get_balance(recipient) == before_recipient_balance + amount_wei
    assert web3.eth.get_balance(vote.address) == 0
    events = vote.events.DebugSTTWithdrawn().process_receipt(receipt, errors=DISCARD)
    assert events[0]["args"]["to"] == recipient
    assert events[0]["args"]["amountWei"] == amount_wei


def test_non_admin_cannot_call_debug_functions(
    web3: Web3,
    contracts: dict[str, Contract],
) -> None:
    vote = contracts["vote"]

    with pytest.raises(Exception, match="only debug admin"):
        vote.functions.debugOnlyVoidVote(1401).transact({"from": web3.eth.accounts[1]})

    with pytest.raises(Exception, match="only debug admin"):
        vote.functions.debugOnlyCancelPendingRequest(1).transact(
            {"from": web3.eth.accounts[1]}
        )

    with pytest.raises(Exception, match="only debug admin"):
        vote.functions.debugOnlyWithdrawAllSTT(web3.eth.accounts[2]).transact(
            {"from": web3.eth.accounts[1]}
        )


def test_mock_fulfillment_is_owner_only(
    web3: Web3,
    contracts: dict[str, Contract],
) -> None:
    vote = contracts["vote"]
    mock_platform = contracts["mock_platform"]
    request_id = request_vote(web3, vote, web3.eth.accounts[1], 700, 1)

    with pytest.raises(Exception, match="only owner"):
        mock_platform.functions.fulfillBool(request_id, True).transact(
            {"from": web3.eth.accounts[1]}
        )

    tx_hash = mock_platform.functions.fulfillBool(request_id, True).transact(
        {"from": web3.eth.accounts[0]}
    )
    web3.eth.wait_for_transaction_receipt(tx_hash)
    assert vote.functions.getTokenVote(700).call() == 1


def test_json_api_uint_probe_records_raw_and_decoded_result(
    web3: Web3,
    compiled_contracts: dict[str, Any],
    contracts: dict[str, Contract],
) -> None:
    mock_platform = contracts["mock_platform"]
    probe = deploy_contract(
        web3,
        compiled_contracts,
        "contracts/JsonApiUintProbe.sol",
        "JsonApiUintProbe",
        [
            mock_platform.address,
            JSON_API_AGENT_ID,
            JSON_API_METHOD_SELECTOR,
            0,
            3,
        ],
    )

    tx_hash = probe.functions.requestUint(
        "https://wrapper.example/owns?collectionId=1&wallet=0x1111111111111111111111111111111111111111&tokenId=1",
        "votingPower",
        0,
    ).transact({"from": web3.eth.accounts[1]})
    receipt = web3.eth.wait_for_transaction_receipt(tx_hash)
    events = probe.events.ProbeRequested().process_receipt(receipt, errors=DISCARD)
    request_id = int(events[0]["args"]["requestId"])

    tx_hash = mock_platform.functions.fulfillUint(request_id, 1).transact(
        {"from": web3.eth.accounts[0]}
    )
    web3.eth.wait_for_transaction_receipt(tx_hash)

    assert probe.functions.pendingRequests(request_id).call() is False
    assert probe.functions.lastRequestId().call() == request_id
    assert probe.functions.lastStatus().call() == 2
    assert probe.functions.lastDecodeOk().call() is True
    assert probe.functions.lastDecodedUint().call() == 1
    assert len(probe.functions.lastRawResult().call()) == 32


def deploy_contract(
    web3: Web3,
    compiled_contracts: dict[str, Any],
    source_path: str,
    contract_name: str,
    constructor_args: list[Any],
) -> Contract:
    contract_interface = compiled_contracts["contracts"][source_path][contract_name]
    abi = contract_interface["abi"]
    bytecode = "0x" + contract_interface["evm"]["bytecode"]["object"]
    factory = web3.eth.contract(abi=abi, bytecode=bytecode)
    tx_hash = factory.constructor(*constructor_args).transact(
        {"from": web3.eth.accounts[0]}
    )
    receipt = web3.eth.wait_for_transaction_receipt(tx_hash)
    assert receipt["status"] == 1
    return web3.eth.contract(address=receipt["contractAddress"], abi=abi)


def fund_contract(web3: Web3, address: str, amount_wei: int) -> None:
    tx_hash = web3.eth.send_transaction(
        {
            "from": web3.eth.accounts[0],
            "to": address,
            "value": amount_wei,
        }
    )
    receipt = web3.eth.wait_for_transaction_receipt(tx_hash)
    assert receipt["status"] == 1


def fulfill_vote(
    web3: Web3,
    mock_platform: Contract,
    request_id: int,
    voting_power: int | bool,
) -> None:
    if isinstance(voting_power, bool):
        voting_power = 1 if voting_power else 0
    tx_hash = mock_platform.functions.fulfillUint(request_id, voting_power).transact(
        {"from": web3.eth.accounts[0]}
    )
    receipt = web3.eth.wait_for_transaction_receipt(tx_hash)
    assert receipt["status"] == 1


def request_vote(
    web3: Web3,
    vote: Contract,
    voter: str,
    token_id: int,
    choice: int,
    collection_id: int = QUILLS_COLLECTION_ID,
) -> int:
    tx_hash = vote.functions.vote(collection_id, token_id, choice).transact(
        {"from": voter}
    )
    receipt = web3.eth.wait_for_transaction_receipt(tx_hash)
    assert receipt["status"] == 1
    events = vote.events.VoteRequested().process_receipt(receipt, errors=DISCARD)
    assert len(events) == 1
    assert events[0]["args"]["collectionId"] == collection_id
    assert events[0]["args"]["tokenId"] == token_id
    return int(events[0]["args"]["requestId"])
