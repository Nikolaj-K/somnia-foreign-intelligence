"""
What: Compile, deploy, and interact with the NFT-gated Somnia voting contract.
Run:  python scripts/somnia_vote_cli.py --config config.local.json preflight
Deps: Python 3.9+; install with `python -m pip install -r requirements.txt`.

This CLI intentionally supports two tracks:
1. Mock-platform track: deploy MockSomniaAgentPlatform, deploy NftGatedVote
   against it, submit a vote, then manually fulfill owns=true/false. This tests
   the contract's async request/callback logic without the live JSON API agent.
2. Real-platform track: deploy a tiny JsonApiUintProbe, then deploy
   NftGatedVote against the official Somnia Agents platform once the public
   wrapper and documented fetchUint path are confirmed.

Secrets:
- Put SOMNIA_PRIVATE_KEY in ignored `.env.local` or export it in the shell.
- Never put private keys in JSON config.
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import shlex
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path
from typing import Any
from typing import Optional

from eth_abi import encode
from eth_account import Account
from eth_utils import function_signature_to_4byte_selector
from rich.console import Console
from rich.logging import RichHandler
from rich.markup import escape
from rich.panel import Panel
from rich.table import Table
from web3 import Web3
from web3.logs import DISCARD

try:
    from solidity_build import compile_project_contracts
    from solidity_build import DEFAULT_SOLC_VERSION
    from solidity_build import resolve_solc_binary as resolve_solc_binary_shared
except ModuleNotFoundError:
    from scripts.solidity_build import compile_project_contracts
    from scripts.solidity_build import DEFAULT_SOLC_VERSION
    from scripts.solidity_build import resolve_solc_binary as resolve_solc_binary_shared


LOGGER = logging.getLogger("somnia-vote")
CONSOLE = Console()
PROJECT_ROOT = Path(__file__).resolve().parent.parent
TOKEN_WEI = Decimal(10) ** 18
ZERO_BYTES4 = "0x00000000"
OWNERSHIP_BOOL_SELECTOR = "owns"
OWNERSHIP_UINT_SELECTOR = "votingPower"
OWNERSHIP_UINT_DECIMALS = 0
OWNERSHIP_RESPONSE_KINDS = {"bool": 0, "uint": 1}
DEFAULT_JSON_API_AGENT_ID = 13174292974160097713
DEFAULT_JSON_API_FETCH_UINT_SIGNATURE = "fetchUint(string,string,uint8)"
DEFAULT_JSON_API_FETCH_UINT_SELECTOR = "0x3bbc1302"
DEFAULT_JSON_API_PRICE_PER_VALIDATOR_STT = "0.03"
DEFAULT_JSON_API_SUBCOMMITTEE_SIZE = 3
DEFAULT_COLLECTIONS = {
    1: {
        "alias": "quills",
        "label": "quills-adventure",
        "display_label": "Quills Adventure",
        "chain": "somnia-mainnet",
        "voting_power": 1,
    },
    2: {
        "alias": "bayc",
        "label": "bored-ape-yacht-club",
        "display_label": "Bored Ape Yacht Club",
        "chain": "ethereum-mainnet",
        "voting_power": 2,
    },
}
COLLECTION_ALIASES = {
    value["alias"]: collection_id
    for collection_id, value in DEFAULT_COLLECTIONS.items()
}


@dataclass(frozen=True)
class NetworkConfig:
    name: str
    chain_id: int
    rpc_url: str
    native_symbol: str
    explorer_url: str
    platform_contract: str


NETWORKS = {
    "testnet": NetworkConfig(
        name="testnet",
        chain_id=50312,
        rpc_url="https://api.infra.testnet.somnia.network/",
        native_symbol="STT",
        explorer_url="https://shannon-explorer.somnia.network",
        platform_contract="0x037Bb9C718F3f7fe5eCBDB0b600D607b52706776",
    ),
    "mainnet": NetworkConfig(
        name="mainnet",
        chain_id=5031,
        rpc_url="https://api.infra.mainnet.somnia.network/",
        native_symbol="SOMI",
        explorer_url="https://explorer.somnia.network",
        platform_contract="0x5E5205CF39E766118C01636bED000A54D93163E6",
    ),
}


@dataclass(frozen=True)
class AppConfig:
    config_path: Path
    network: NetworkConfig
    rpc_url: str
    private_key: str
    wallet_address: str
    vote_contract_address: Optional[str]
    probe_contract_address: Optional[str]
    mock_platform_address: Optional[str]
    platform_contract: str
    json_api_agent_id: int
    json_api_method_selector: str
    ownership_response_kind: str
    agent_price_per_validator_wei: int
    agent_subcommittee_size: int
    base_ownership_url: str
    reward_wei: int
    max_choice: int
    request_deposit_wei: int
    gas_limit: int
    gas_price_gwei: Optional[Decimal]
    solc_binary: Path


def main() -> None:
    parser = build_arg_parser()
    args = parser.parse_args()
    configure_logging()

    if args.command == "selector":
        selector = function_signature_to_4byte_selector(args.signature).hex()
        print("0x" + selector)
        return

    if args.command == "compile":
        solc_binary = load_solc_binary_for_compile(args.config)
        compiled = compile_contracts(solc_binary)
        print_contracts(compiled)
        return

    if args.command == "live-defaults":
        print_live_defaults()
        return

    load_dotenv_local(PROJECT_ROOT / ".env.local")
    config = load_config(args.config)
    web3 = Web3(Web3.HTTPProvider(config.rpc_url, request_kwargs={"timeout": 20}))
    if args.command == "preflight":
        run_preflight(web3, config)
    elif args.command == "deploy-mock-platform":
        deploy_mock_platform(web3, config, args)
    elif args.command == "deploy-vote":
        deploy_vote_contract(web3, config, args)
    elif args.command == "deploy-probe":
        deploy_probe_contract(web3, config, args)
    elif args.command == "probe-request":
        submit_probe_request(web3, config, args)
    elif args.command == "probe-read":
        read_probe_state(web3, config, args)
    elif args.command == "fund":
        fund_contract(web3, config, args)
    elif args.command == "vote":
        submit_vote(web3, config, args)
    elif args.command == "mock-fulfill":
        mock_fulfill(web3, config, args)
    elif args.command == "read":
        read_token_vote(web3, config, args)
    elif args.command == "count":
        read_vote_count(web3, config, args)
    elif args.command == "poll-info":
        read_poll_info(web3, config, args)
    elif args.command == "collections":
        read_collections(web3, config, args)
    elif args.command in {"results", "leader"}:
        read_results(web3, config, args)
    elif args.command == "pending":
        read_pending_vote(web3, config, args)
    elif args.command == "set-url":
        set_base_url(web3, config, args)
    elif args.command == "withdraw":
        withdraw(web3, config, args)
    elif args.command == "set-agent-config":
        set_agent_config(web3, config, args)
    elif args.command == "set-reward":
        set_reward(web3, config, args)
    elif args.command == "set-pending-timeout":
        set_pending_timeout(web3, config, args)
    elif args.command == "release-expired":
        release_expired_pending_vote(web3, config, args)
    elif args.command == "pause":
        pause_contract(web3, config, args)
    elif args.command == "unpause":
        unpause_contract(web3, config, args)
    elif args.command == "transfer-ownership":
        transfer_ownership(web3, config, args)
    elif args.command == "debug-void-vote":
        debug_void_vote(web3, config, args)
    elif args.command == "debug-cancel-pending":
        debug_cancel_pending(web3, config, args)
    elif args.command == "debug-withdraw-stt":
        debug_withdraw_stt(web3, config, args)
    elif args.command == "debug-withdraw-all-stt":
        debug_withdraw_all_stt(web3, config, args)
    elif args.command == "live-defaults":
        print_live_defaults()
    else:
        raise SystemExit(f"Unhandled command: {args.command}")


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Somnia NFT-gated vote CLI")
    parser.add_argument(
        "--config",
        default="config.local.json",
        help="Ignored local JSON config path.",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    subparsers.add_parser("compile", help="Compile contracts without RPC access.")
    subparsers.add_parser("preflight", help="Read-only RPC and config checks.")

    selector_parser = subparsers.add_parser(
        "selector",
        help="Print bytes4 selector for a function signature.",
    )
    selector_parser.add_argument(
        "signature",
        help="Example: fetchUint(string,string,uint8)",
    )

    subparsers.add_parser(
        "live-defaults",
        help="Print documented Somnia JSON API fetchUint defaults.",
    )

    mock_parser = subparsers.add_parser(
        "deploy-mock-platform",
        help="Deploy MockSomniaAgentPlatform for callback-flow testing.",
    )
    mock_parser.add_argument("--request-deposit-stt", default=None)

    deploy_parser = subparsers.add_parser("deploy-vote", help="Deploy NftGatedVote.")
    deploy_parser.add_argument(
        "--platform-address",
        default=None,
        help="Explicit platform address. Use only when you know the target.",
    )
    deploy_parser.add_argument(
        "--use-mock-platform",
        action="store_true",
        help="Deploy against config.mock_platform_address; placeholder JSON settings allowed.",
    )
    deploy_parser.add_argument(
        "--use-config-platform",
        action="store_true",
        help="Deploy against config.platform_contract; live JSON settings must be non-placeholder.",
    )
    deploy_parser.add_argument("--base-url", default=None)
    deploy_parser.add_argument("--reward-stt", default=None)
    deploy_parser.add_argument("--json-api-agent-id", type=int, default=None)
    deploy_parser.add_argument("--json-api-method-selector", default=None)
    deploy_parser.add_argument(
        "--ownership-response-kind",
        choices=sorted(OWNERSHIP_RESPONSE_KINDS),
        default=None,
        help="Use uint for documented fetchUint/votingPower live path.",
    )
    deploy_parser.add_argument("--agent-price-per-validator-stt", default=None)
    deploy_parser.add_argument("--agent-subcommittee-size", type=int, default=None)
    deploy_parser.add_argument("--max-choice", type=int, default=None)

    probe_deploy_parser = subparsers.add_parser(
        "deploy-probe",
        help="Deploy JsonApiUintProbe against the configured/live platform.",
    )
    probe_deploy_parser.add_argument("--platform-address", default=None)
    probe_deploy_parser.add_argument(
        "--use-config-platform",
        action="store_true",
        help="Deploy against config.platform_contract.",
    )
    probe_deploy_parser.add_argument("--json-api-agent-id", type=int, default=None)
    probe_deploy_parser.add_argument("--json-api-method-selector", default=None)
    probe_deploy_parser.add_argument("--agent-price-per-validator-stt", default=None)
    probe_deploy_parser.add_argument(
        "--agent-subcommittee-size", type=int, default=None
    )

    probe_request_parser = subparsers.add_parser(
        "probe-request",
        help="Submit a documented fetchUint probe request.",
    )
    add_probe_contract_argument(probe_request_parser)
    probe_request_parser.add_argument("--url", required=True)
    probe_request_parser.add_argument(
        "--selector-path", default=OWNERSHIP_UINT_SELECTOR
    )
    probe_request_parser.add_argument(
        "--decimals", type=int, default=OWNERSHIP_UINT_DECIMALS
    )
    probe_request_parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print payload and value without submitting.",
    )

    probe_read_parser = subparsers.add_parser(
        "probe-read",
        help="Read JsonApiUintProbe state.",
    )
    add_probe_contract_argument(probe_read_parser)

    fund_parser = subparsers.add_parser("fund", help="Send STT/SOMI to a contract.")
    add_vote_contract_argument(fund_parser)
    fund_parser.add_argument("--amount-stt", required=True)

    vote_parser = subparsers.add_parser(
        "vote",
        help="Call vote(collectionId, tokenId, choice).",
    )
    add_vote_contract_argument(vote_parser)
    add_collection_argument(vote_parser)
    vote_parser.add_argument("--token-id", required=True, type=int)
    vote_parser.add_argument("--choice", required=True, type=int)
    vote_parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print URL, payload, and request value without submitting.",
    )

    fulfill_parser = subparsers.add_parser(
        "mock-fulfill",
        help="Deliver owns=true/false through MockSomniaAgentPlatform.",
    )
    fulfill_parser.add_argument("--mock-platform-address", default=None)
    fulfill_parser.add_argument("--request-id", required=True, type=int)
    fulfill_parser.add_argument(
        "--owns",
        default=None,
        choices=["true", "false"],
        help="Bool result to ABI-encode into the callback.",
    )
    fulfill_parser.add_argument(
        "--voting-power",
        type=int,
        default=None,
        help="Uint votingPower result to ABI-encode into the callback.",
    )

    read_parser = subparsers.add_parser("read", help="Read vote state for token ID.")
    add_vote_contract_argument(read_parser)
    add_collection_argument(read_parser)
    read_parser.add_argument("--token-id", required=True, type=int)

    count_parser = subparsers.add_parser("count", help="Read count for one choice.")
    add_vote_contract_argument(count_parser)
    count_parser.add_argument("--choice", required=True, type=int)

    poll_info_parser = subparsers.add_parser(
        "poll-info",
        help="Read AI poll question, choices, and voting contract address.",
    )
    add_vote_contract_argument(poll_info_parser)

    collections_parser = subparsers.add_parser(
        "collections",
        help="Read supported NFT voting collections and weights.",
    )
    add_vote_contract_argument(collections_parser)

    results_parser = subparsers.add_parser(
        "results",
        help="Read all choice counts and current leader/tie state.",
    )
    add_vote_contract_argument(results_parser)

    leader_parser = subparsers.add_parser(
        "leader",
        help="Alias for results.",
    )
    add_vote_contract_argument(leader_parser)

    pending_parser = subparsers.add_parser(
        "pending",
        help="Read pendingVotes(requestId).",
    )
    add_vote_contract_argument(pending_parser)
    pending_parser.add_argument("--request-id", required=True, type=int)

    set_url_parser = subparsers.add_parser("set-url", help="Update wrapper base URL.")
    add_vote_contract_argument(set_url_parser)
    set_url_parser.add_argument("--url", required=True)

    withdraw_parser = subparsers.add_parser(
        "withdraw",
        help="Withdraw native token from the vote contract.",
    )
    add_vote_contract_argument(withdraw_parser)
    withdraw_parser.add_argument("--to", required=True)
    withdraw_parser.add_argument("--amount-stt", required=True)

    set_agent_parser = subparsers.add_parser(
        "set-agent-config",
        help="Update JSON API agent ID, method selector, price, and subcommittee size.",
    )
    add_vote_contract_argument(set_agent_parser)
    set_agent_parser.add_argument("--json-api-agent-id", required=True, type=int)
    set_agent_parser.add_argument("--json-api-method-selector", required=True)
    set_agent_parser.add_argument(
        "--ownership-response-kind",
        choices=sorted(OWNERSHIP_RESPONSE_KINDS),
        default="uint",
    )
    set_agent_parser.add_argument("--agent-price-per-validator-stt", required=True)
    set_agent_parser.add_argument("--agent-subcommittee-size", required=True, type=int)

    set_reward_parser = subparsers.add_parser(
        "set-reward", help="Update reward amount."
    )
    add_vote_contract_argument(set_reward_parser)
    set_reward_parser.add_argument("--reward-stt", required=True)

    set_timeout_parser = subparsers.add_parser(
        "set-pending-timeout",
        help="Update pending token-request timeout in seconds.",
    )
    add_vote_contract_argument(set_timeout_parser)
    set_timeout_parser.add_argument("--seconds", required=True, type=int)

    release_parser = subparsers.add_parser(
        "release-expired",
        help="Release an expired pending vote request.",
    )
    add_vote_contract_argument(release_parser)
    release_parser.add_argument("--request-id", required=True, type=int)

    pause_parser = subparsers.add_parser("pause", help="Pause new vote requests.")
    add_vote_contract_argument(pause_parser)

    unpause_parser = subparsers.add_parser("unpause", help="Unpause new vote requests.")
    add_vote_contract_argument(unpause_parser)

    transfer_parser = subparsers.add_parser(
        "transfer-ownership",
        help="Transfer contract ownership.",
    )
    add_vote_contract_argument(transfer_parser)
    transfer_parser.add_argument("--new-owner", required=True)

    debug_void_parser = subparsers.add_parser(
        "debug-void-vote",
        help="DEMO ONLY: admin clears a recorded token vote.",
    )
    add_vote_contract_argument(debug_void_parser)
    add_collection_argument(debug_void_parser)
    debug_void_parser.add_argument("--token-id", required=True, type=int)
    debug_void_parser.add_argument("--dry-run", action="store_true")

    debug_cancel_parser = subparsers.add_parser(
        "debug-cancel-pending",
        help="DEMO ONLY: admin clears a stuck pending request.",
    )
    add_vote_contract_argument(debug_cancel_parser)
    debug_cancel_parser.add_argument("--request-id", required=True, type=int)
    debug_cancel_parser.add_argument("--dry-run", action="store_true")

    debug_withdraw_parser = subparsers.add_parser(
        "debug-withdraw-stt",
        help="DEMO ONLY: admin withdraws a specified STT amount.",
    )
    add_vote_contract_argument(debug_withdraw_parser)
    debug_withdraw_parser.add_argument("--to", required=True)
    debug_withdraw_parser.add_argument("--amount-stt", required=True)
    debug_withdraw_parser.add_argument("--dry-run", action="store_true")

    debug_withdraw_all_parser = subparsers.add_parser(
        "debug-withdraw-all-stt",
        help="DEMO ONLY: admin withdraws the full contract balance.",
    )
    add_vote_contract_argument(debug_withdraw_all_parser)
    debug_withdraw_all_parser.add_argument("--to", required=True)
    debug_withdraw_all_parser.add_argument("--dry-run", action="store_true")

    return parser


def add_vote_contract_argument(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--contract-address",
        default=None,
        help=(
            "Deployed NftGatedVote contract address. This is not the voter wallet; "
            "the voter is from_address from the local private key."
        ),
    )


def add_collection_argument(parser: argparse.ArgumentParser) -> None:
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument(
        "--collection-id",
        type=int,
        help="Voting credential collection ID. Use 1 for Quills or 2 for BAYC.",
    )
    group.add_argument(
        "--collection",
        choices=sorted(COLLECTION_ALIASES),
        help="Friendly collection selector: quills or bayc.",
    )


def add_probe_contract_argument(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--probe-contract-address",
        default=None,
        help=(
            "Deployed JsonApiUintProbe contract address. "
            "Use PROBE_CONTRACT_ADDRESS in shell examples."
        ),
    )


def configure_logging() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(message)s",
        datefmt="[%X]",
        handlers=[RichHandler(rich_tracebacks=True, show_path=False, markup=True)],
    )


def styled(value: Any, style: str) -> str:
    return f"[{style}]{escape(str(value))}[/]"


def address_text(value: Any) -> str:
    return styled(value, "cyan")


def url_text(value: Any) -> str:
    return styled(value, "blue")


def success_text(value: Any) -> str:
    return styled(value, "green")


def warning_text(value: Any) -> str:
    return styled(value, "yellow")


def failure_text(value: Any) -> str:
    return styled(value, "red")


def bool_text(value: bool) -> str:
    return success_text(value) if value else failure_text(value)


def print_kv_panel(
    title: str,
    rows: list[tuple[str, Any, Optional[str]]],
    border_style: str = "cyan",
) -> None:
    table = Table.grid(padding=(0, 2))
    table.add_column(style="bold", no_wrap=True)
    table.add_column(overflow="fold")
    for key, value, style in rows:
        rendered = styled(value, style) if style else escape(str(value))
        table.add_row(key, rendered)
    CONSOLE.print(Panel(table, title=title, border_style=border_style))


def load_dotenv_local(path: Path) -> None:
    if not path.exists():
        return
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        os.environ.setdefault(key, value)


def load_config(path_value: Any) -> AppConfig:
    config_path = Path(path_value)
    if not config_path.is_absolute():
        config_path = PROJECT_ROOT / config_path
    assert config_path.exists(), f"Missing config file: {config_path}"

    raw = json.loads(config_path.read_text(encoding="utf-8"))
    assert isinstance(raw, dict), "Config root must be a JSON object"
    assert "private_key" not in raw, "Never put private_key in JSON config"

    network_name = require_str(raw, "network", "testnet").lower()
    assert network_name in NETWORKS, f"Unknown network: {network_name}"
    network = NETWORKS[network_name]
    rpc_url = raw.get("rpc_url") or network.rpc_url
    assert isinstance(rpc_url, str) and rpc_url.startswith("http")

    private_key = os.environ.get("SOMNIA_PRIVATE_KEY")
    assert private_key, "Set SOMNIA_PRIVATE_KEY in .env.local or the shell"
    wallet_address = Account.from_key(private_key).address
    configured_wallet = raw.get("wallet_address")
    if configured_wallet:
        configured_wallet = Web3.to_checksum_address(configured_wallet)
        assert (
            configured_wallet == wallet_address
        ), "wallet_address does not match SOMNIA_PRIVATE_KEY-derived address"

    solc_binary = resolve_solc_binary(raw.get("solc_binary"))

    return AppConfig(
        config_path=config_path,
        network=network,
        rpc_url=rpc_url,
        private_key=private_key,
        wallet_address=wallet_address,
        vote_contract_address=optional_address(raw.get("vote_contract_address")),
        probe_contract_address=optional_address(raw.get("probe_contract_address")),
        mock_platform_address=optional_address(raw.get("mock_platform_address")),
        platform_contract=optional_address(raw.get("platform_contract"))
        or network.platform_contract,
        json_api_agent_id=require_int(raw, "json_api_agent_id", 0, minimum=0),
        json_api_method_selector=require_bytes4(
            raw.get("json_api_method_selector", "0x00000000")
        ),
        ownership_response_kind=require_response_kind(
            raw.get("ownership_response_kind", "uint")
        ),
        agent_price_per_validator_wei=tokens_to_wei(
            require_str(raw, "agent_price_per_validator_stt", "0")
        ),
        agent_subcommittee_size=require_int(
            raw,
            "agent_subcommittee_size",
            3,
            minimum=1,
        ),
        base_ownership_url=require_str(
            raw,
            "base_ownership_url",
            "https://example.com/owns",
        ),
        reward_wei=tokens_to_wei(require_str(raw, "reward_stt", "1.02")),
        max_choice=require_int(raw, "max_choice", 3, minimum=1, maximum=255),
        request_deposit_wei=tokens_to_wei(require_str(raw, "request_deposit_stt", "0")),
        gas_limit=require_int(raw, "gas_limit", 3_000_000, minimum=21_000),
        gas_price_gwei=optional_decimal(raw.get("gas_price_gwei")),
        solc_binary=solc_binary,
    )


def load_solc_binary_for_compile(path_value: Any) -> Path:
    config_path = Path(path_value)
    if not config_path.is_absolute():
        config_path = PROJECT_ROOT / config_path
    if not config_path.exists():
        return resolve_solc_binary(None)
    raw = json.loads(config_path.read_text(encoding="utf-8"))
    assert isinstance(raw, dict), "Config root must be a JSON object"
    return resolve_solc_binary(raw.get("solc_binary"))


def resolve_solc_binary(raw_value: Any) -> Path:
    return resolve_solc_binary_from_shared(raw_value)


def resolve_solc_binary_from_shared(raw_value: Any) -> Path:
    return resolve_solc_binary_shared(
        project_root=PROJECT_ROOT,
        configured_path=raw_value,
        allow_install=True,
    )


def run_preflight(web3: Web3, config: AppConfig) -> None:
    assert web3.is_connected(), f"Could not connect to RPC: {config.rpc_url}"
    chain_id = web3.eth.chain_id
    assert (
        chain_id == config.network.chain_id
    ), f"RPC chain_id={chain_id} does not match expected {config.network.chain_id}"

    balance_wei = web3.eth.get_balance(config.wallet_address)
    platform_address = Web3.to_checksum_address(config.platform_contract)
    platform_code = web3.eth.get_code(platform_address)
    vote_code_len = 0
    if config.vote_contract_address is not None:
        vote_code_len = len(web3.eth.get_code(config.vote_contract_address))
    probe_code_len = 0
    if config.probe_contract_address is not None:
        probe_code_len = len(web3.eth.get_code(config.probe_contract_address))

    print_kv_panel(
        "Preflight",
        [
            ("network", f"{config.network.name} chain_id={chain_id}", "green"),
            ("from_address", config.wallet_address, "cyan"),
            (
                "wallet_balance",
                f"{web3.from_wei(balance_wei, 'ether')} {config.network.native_symbol}",
                "green" if balance_wei > 0 else "yellow",
            ),
            (
                "platform_contract",
                f"{platform_address} code_bytes={len(platform_code)}",
                "green" if platform_code else "red",
            ),
            (
                "vote_contract_address",
                f"{config.vote_contract_address} code_bytes={vote_code_len}",
                "green" if vote_code_len else "yellow",
            ),
            (
                "probe_contract_address",
                f"{config.probe_contract_address} code_bytes={probe_code_len}",
                "green" if probe_code_len else "yellow",
            ),
            ("json_api_agent_id", config.json_api_agent_id, "cyan"),
            ("json_api_method_selector", config.json_api_method_selector, "cyan"),
            ("ownership_response_kind", config.ownership_response_kind, "green"),
            (
                "reward",
                f"{wei_to_token(config.reward_wei)} {config.network.native_symbol}",
                "cyan",
            ),
            ("max_choice", config.max_choice, "cyan"),
            ("solc_binary", config.solc_binary, None),
        ],
        border_style="green",
    )


def compile_contracts(solc_binary: Path) -> dict[str, Any]:
    return compile_project_contracts(PROJECT_ROOT, solc_binary)


def print_contracts(compiled: dict[str, Any]) -> None:
    for source_path, contracts in compiled["contracts"].items():
        for contract_name in contracts:
            print(f"{source_path}:{contract_name}")


def get_contract_interface(
    compiled: dict[str, Any],
    source_path: str,
    contract_name: str,
) -> tuple[list[dict[str, Any]], str]:
    contract = compiled["contracts"][source_path][contract_name]
    bytecode = contract["evm"]["bytecode"]["object"]
    assert bytecode, f"Missing bytecode for {contract_name}"
    return contract["abi"], "0x" + bytecode


def deploy_mock_platform(
    web3: Web3, config: AppConfig, args: argparse.Namespace
) -> None:
    request_deposit_wei = (
        tokens_to_wei(args.request_deposit_stt)
        if args.request_deposit_stt is not None
        else config.request_deposit_wei
    )
    abi, bytecode = get_contract_interface(
        compile_contracts(config.solc_binary),
        "contracts/test/MockSomniaAgentPlatform.sol",
        "MockSomniaAgentPlatform",
    )
    factory = web3.eth.contract(abi=abi, bytecode=bytecode)
    tx = factory.constructor(request_deposit_wei)
    receipt = sign_send_wait(web3, config, tx, "deploy MockSomniaAgentPlatform")
    address = Web3.to_checksum_address(receipt["contractAddress"])
    print_kv_panel(
        "Mock Platform Deployed",
        [
            ("mock_platform_address", address, "cyan"),
            ("config.local.json entry", f'"mock_platform_address": "{address}"', None),
        ],
        border_style="green",
    )


def deploy_vote_contract(
    web3: Web3, config: AppConfig, args: argparse.Namespace
) -> None:
    platform_address, using_mock_platform = resolve_deploy_platform(config, args)

    json_api_agent_id = (
        args.json_api_agent_id
        if args.json_api_agent_id is not None
        else config.json_api_agent_id
    )
    json_api_method_selector = require_bytes4(
        args.json_api_method_selector or config.json_api_method_selector
    )
    ownership_response_kind = (
        args.ownership_response_kind or config.ownership_response_kind
    )
    agent_price_per_validator_wei = (
        tokens_to_wei(args.agent_price_per_validator_stt)
        if args.agent_price_per_validator_stt is not None
        else config.agent_price_per_validator_wei
    )
    agent_subcommittee_size = (
        args.agent_subcommittee_size
        if args.agent_subcommittee_size is not None
        else config.agent_subcommittee_size
    )
    base_url = args.base_url or config.base_ownership_url
    assert_valid_base_ownership_url(base_url)
    if not using_mock_platform:
        assert_live_agent_settings(
            json_api_agent_id=json_api_agent_id,
            json_api_method_selector=json_api_method_selector,
            ownership_response_kind=ownership_response_kind,
            base_ownership_url=base_url,
            agent_price_per_validator_wei=agent_price_per_validator_wei,
        )
    constructor_args = [
        Web3.to_checksum_address(platform_address),
        json_api_agent_id,
        json_api_method_selector,
        agent_price_per_validator_wei,
        agent_subcommittee_size,
        base_url,
        OWNERSHIP_RESPONSE_KINDS[ownership_response_kind],
        (
            tokens_to_wei(args.reward_stt)
            if args.reward_stt is not None
            else config.reward_wei
        ),
        args.max_choice if args.max_choice is not None else config.max_choice,
    ]

    abi, bytecode = get_contract_interface(
        compile_contracts(config.solc_binary),
        "contracts/NftGatedVote.sol",
        "NftGatedVote",
    )
    factory = web3.eth.contract(abi=abi, bytecode=bytecode)
    receipt = sign_send_wait(
        web3,
        config,
        factory.constructor(*constructor_args),
        "deploy NftGatedVote",
    )
    address = Web3.to_checksum_address(receipt["contractAddress"])
    deployed = web3.eth.contract(address=address, abi=abi)
    callback_selector = deployed.functions.handleResponseSelector().call().hex()
    if not callback_selector.startswith("0x"):
        callback_selector = "0x" + callback_selector

    print_kv_panel(
        "NftGatedVote Deployed",
        [
            ("vote_contract_address", address, "cyan"),
            ("handle_response_selector", callback_selector, "cyan"),
            ("poll_question", deployed.functions.pollQuestion().call(), "green"),
            ("config.local.json entry", f'"vote_contract_address": "{address}"', None),
        ],
        border_style="green",
    )


def deploy_probe_contract(
    web3: Web3, config: AppConfig, args: argparse.Namespace
) -> None:
    platform_address = resolve_probe_platform(config, args)
    json_api_agent_id = (
        args.json_api_agent_id
        if args.json_api_agent_id is not None
        else config.json_api_agent_id
    )
    json_api_method_selector = require_bytes4(
        args.json_api_method_selector or config.json_api_method_selector
    )
    agent_price_per_validator_wei = (
        tokens_to_wei(args.agent_price_per_validator_stt)
        if args.agent_price_per_validator_stt is not None
        else config.agent_price_per_validator_wei
    )
    agent_subcommittee_size = (
        args.agent_subcommittee_size
        if args.agent_subcommittee_size is not None
        else config.agent_subcommittee_size
    )
    assert_live_agent_settings(
        json_api_agent_id=json_api_agent_id,
        json_api_method_selector=json_api_method_selector,
        ownership_response_kind="uint",
        base_ownership_url="https://live-probe.invalid/owns",
        agent_price_per_validator_wei=agent_price_per_validator_wei,
        allow_example_url=True,
    )

    abi, bytecode = get_contract_interface(
        compile_contracts(config.solc_binary),
        "contracts/JsonApiUintProbe.sol",
        "JsonApiUintProbe",
    )
    factory = web3.eth.contract(abi=abi, bytecode=bytecode)
    receipt = sign_send_wait(
        web3,
        config,
        factory.constructor(
            Web3.to_checksum_address(platform_address),
            json_api_agent_id,
            json_api_method_selector,
            agent_price_per_validator_wei,
            agent_subcommittee_size,
        ),
        "deploy JsonApiUintProbe",
    )
    address = Web3.to_checksum_address(receipt["contractAddress"])
    deployed = web3.eth.contract(address=address, abi=abi)
    callback_selector = deployed.functions.handleResponseSelector().call().hex()
    if not callback_selector.startswith("0x"):
        callback_selector = "0x" + callback_selector

    print_kv_panel(
        "JsonApiUintProbe Deployed",
        [
            ("probe_contract_address", address, "cyan"),
            ("handle_response_selector", callback_selector, "cyan"),
            ("config.local.json entry", f'"probe_contract_address": "{address}"', None),
        ],
        border_style="green",
    )


def submit_probe_request(
    web3: Web3, config: AppConfig, args: argparse.Namespace
) -> None:
    contract = probe_contract(web3, config, args.probe_contract_address)
    assert args.decimals >= 0 and args.decimals <= 255, "decimals must fit uint8"
    assert_valid_probe_url(args.url)
    payload = bytes.fromhex(
        bytes4_to_hex(contract.functions.jsonApiMethodSelector().call())[2:]
    ) + encode(
        ["string", "string", "uint8"], [args.url, args.selector_path, args.decimals]
    )
    request_value_wei = contract.functions.quoteRequestValueWei().call()
    result = {
        "contract_address": contract.address,
        "from_address": config.wallet_address,
        "json_api_agent_id": contract.functions.jsonApiAgentId().call(),
        "method_selector": bytes4_to_hex(
            contract.functions.jsonApiMethodSelector().call()
        ),
        "selector_path": args.selector_path,
        "decimals": args.decimals,
        "url": args.url,
        "payload_hex": Web3.to_hex(payload),
        "request_value_wei": request_value_wei,
        "request_value_stt": str(wei_to_token(request_value_wei)),
    }
    if args.dry_run:
        print_kv_panel(
            "Probe Request Dry Run",
            [
                ("probe_contract_address", contract.address, "cyan"),
                ("from_address", config.wallet_address, "cyan"),
                ("json_api_agent_id", result["json_api_agent_id"], "cyan"),
                ("method_selector", result["method_selector"], "cyan"),
                ("selector_path", args.selector_path, "green"),
                ("decimals", args.decimals, "green"),
                ("url", args.url, "blue"),
                ("request_value_stt", result["request_value_stt"], "yellow"),
                ("payload_hex", result["payload_hex"], None),
            ],
            border_style="yellow",
        )
        return

    print_kv_panel(
        "Probe Request",
        [
            ("probe_contract_address", contract.address, "cyan"),
            ("from_address", config.wallet_address, "cyan"),
            ("url", args.url, "blue"),
            ("selector_path", args.selector_path, "green"),
            ("request_value_stt", result["request_value_stt"], "yellow"),
        ],
        border_style="cyan",
    )
    receipt = sign_send_wait(
        web3,
        config,
        contract.functions.requestUint(args.url, args.selector_path, args.decimals),
        "probe requestUint",
        value_wei=request_value_wei,
    )
    events = contract.events.ProbeRequested().process_receipt(receipt, errors=DISCARD)
    for event in events:
        print_kv_panel(
            "Probe Requested",
            [
                ("request_id", event["args"]["requestId"], "cyan"),
                ("request_value_wei", event["args"]["requestValueWei"], "yellow"),
            ],
            border_style="green",
        )


def read_probe_state(web3: Web3, config: AppConfig, args: argparse.Namespace) -> None:
    contract = probe_contract(web3, config, args.probe_contract_address)
    last_request_id = contract.functions.lastRequestId().call()
    raw_result = contract.functions.lastRawResult().call()
    decode_ok = contract.functions.lastDecodeOk().call()
    decoded_uint = contract.functions.lastDecodedUint().call()
    pending = (
        contract.functions.pendingRequests(last_request_id).call()
        if last_request_id
        else False
    )
    print_kv_panel(
        "Probe State",
        [
            ("probe_contract_address", contract.address, "cyan"),
            ("last_request_id", last_request_id, "cyan"),
            ("last_status", contract.functions.lastStatus().call(), "green"),
            ("last_decode_ok", decode_ok, "green" if decode_ok else "red"),
            (
                "last_decoded_uint",
                decoded_uint,
                "green" if decoded_uint == 1 else "yellow",
            ),
            ("last_raw_result", Web3.to_hex(raw_result), None),
            ("last_url", contract.functions.lastUrl().call(), "blue"),
            (
                "last_selector_path",
                contract.functions.lastSelectorPath().call(),
                "green",
            ),
            ("last_decimals", contract.functions.lastDecimals().call(), "green"),
            ("pending", pending, "yellow" if pending else "green"),
        ],
        border_style=(
            "green" if decode_ok and decoded_uint == 1 and not pending else "yellow"
        ),
    )


def fund_contract(web3: Web3, config: AppConfig, args: argparse.Namespace) -> None:
    contract_address = resolve_contract_address(config, args.contract_address)
    value_wei = tokens_to_wei(args.amount_stt)
    print_kv_panel(
        "Fund Contract",
        [
            ("vote_contract_address", contract_address, "cyan"),
            ("from_address", config.wallet_address, "cyan"),
            ("amount", f"{args.amount_stt} {config.network.native_symbol}", "green"),
        ],
        border_style="cyan",
    )
    tx = {
        "to": contract_address,
        "value": value_wei,
    }
    sign_send_wait(web3, config, tx, f"fund {contract_address}")


def submit_vote(web3: Web3, config: AppConfig, args: argparse.Namespace) -> None:
    contract = vote_contract(web3, config, args.contract_address)
    collection_id = resolve_collection_id(args)
    if args.dry_run:
        print_vote_dry_run(web3, config, contract, args, collection_id)
        return
    assert_contract_is_ready_for_spendful_vote(config, contract)
    request_value_wei = contract.functions.quoteRequestValueWei().call()
    reward_wei = contract.functions.rewardWei().call()
    assert_vote_contract_balance_sufficient(
        web3=web3,
        config=config,
        contract=contract,
        request_value_wei=request_value_wei,
        reward_wei=reward_wei,
        config_path=args.config,
    )
    print_kv_panel(
        "Vote Request",
        [
            ("vote_contract_address", contract.address, "cyan"),
            ("from_address", config.wallet_address, "cyan"),
            ("collection_id", collection_id, "cyan"),
            (
                "collection_label",
                safe_collection_label(contract, collection_id),
                "green",
            ),
            (
                "target_chain",
                safe_collection_chain_label(contract, collection_id),
                "green",
            ),
            (
                "voting_power",
                safe_collection_voting_power(contract, collection_id),
                "yellow",
            ),
            ("token_id", args.token_id, "cyan"),
            ("choice", args.choice, "green"),
            (
                "choice_label",
                safe_choice_label(contract, args.choice),
                "green",
            ),
        ],
        border_style="cyan",
    )
    tx = contract.functions.vote(collection_id, args.token_id, args.choice)
    receipt = sign_send_wait(web3, config, tx, "vote")
    events = contract.events.VoteRequested().process_receipt(receipt, errors=DISCARD)
    for event in events:
        event_args = event["args"]
        LOGGER.info("request_id=%s", event_args["requestId"])
        LOGGER.info("voter=%s", event_args["voter"])
        LOGGER.info("collection_id=%s", event_args["collectionId"])
        LOGGER.info("token_id=%s", event_args["tokenId"])
        LOGGER.info("choice=%s", event_args["choice"])
        LOGGER.info("ownership_url=%s", event_args["url"])
        LOGGER.info("request_value_wei=%s", event_args["requestValueWei"])
    if events:
        event_args = events[0]["args"]
        print(
            build_vote_next_checks_block(
                config_path=args.config,
                contract_address=contract.address,
                request_id=event_args["requestId"],
                collection_id=event_args["collectionId"],
                token_id=event_args["tokenId"],
                choice=event_args["choice"],
            )
        )


def build_vote_next_checks_block(
    config_path: Any,
    contract_address: str,
    request_id: Any,
    collection_id: Any,
    token_id: Any,
    choice: Any,
) -> str:
    config_arg = shlex.quote(str(config_path))
    return "\n".join(
        [
            "next checks:",
            f'VOTE_CONTRACT_ADDRESS="{contract_address}"',
            f'REQUEST_ID="{request_id}"',
            "",
            f"python scripts/somnia_vote_cli.py --config {config_arg} pending \\",
            '  --contract-address "$VOTE_CONTRACT_ADDRESS" \\',
            '  --request-id "$REQUEST_ID"',
            "",
            f"python scripts/somnia_vote_cli.py --config {config_arg} read \\",
            '  --contract-address "$VOTE_CONTRACT_ADDRESS" \\',
            f"  --collection-id {collection_id} \\",
            f"  --token-id {token_id}",
            "",
            f"python scripts/somnia_vote_cli.py --config {config_arg} count \\",
            '  --contract-address "$VOTE_CONTRACT_ADDRESS" \\',
            f"  --choice {choice}",
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


def mock_fulfill(web3: Web3, config: AppConfig, args: argparse.Namespace) -> None:
    address = args.mock_platform_address or config.mock_platform_address
    assert address, "Need --mock-platform-address or mock_platform_address in config"
    abi, _ = get_contract_interface(
        compile_contracts(config.solc_binary),
        "contracts/test/MockSomniaAgentPlatform.sol",
        "MockSomniaAgentPlatform",
    )
    contract = web3.eth.contract(address=Web3.to_checksum_address(address), abi=abi)
    assert (
        args.owns is not None or args.voting_power is not None
    ), "Provide --owns true/false or --voting-power <uint>"
    assert not (
        args.owns is not None and args.voting_power is not None
    ), "Choose only one of --owns or --voting-power"
    if args.voting_power is not None:
        assert args.voting_power >= 0, "voting power must be non-negative"
        sign_send_wait(
            web3,
            config,
            contract.functions.fulfillUint(args.request_id, args.voting_power),
            f"mock fulfill votingPower={args.voting_power}",
        )
        return

    owns = args.owns == "true"
    sign_send_wait(
        web3,
        config,
        contract.functions.fulfillBool(args.request_id, owns),
        f"mock fulfill owns={owns}",
    )


def read_token_vote(web3: Web3, config: AppConfig, args: argparse.Namespace) -> None:
    contract = vote_contract(web3, config, args.contract_address)
    collection_id = resolve_collection_id(args)
    has_voted = contract.functions.hasTokenVoted(collection_id, args.token_id).call()
    choice = contract.functions.getTokenVote(collection_id, args.token_id).call()
    voter = contract.functions.tokenVoter(collection_id, args.token_id).call()
    voting_power = contract.functions.tokenVotingPower(
        collection_id,
        args.token_id,
    ).call()
    pending_request_id = contract.functions.tokenPendingRequest(
        collection_id,
        args.token_id,
    ).call()
    balance = web3.eth.get_balance(contract.address)
    print_kv_panel(
        "Token Vote",
        [
            ("vote_contract_address", contract.address, "cyan"),
            ("collection_id", collection_id, "cyan"),
            (
                "collection_label",
                safe_collection_label(contract, collection_id),
                "green",
            ),
            (
                "target_chain",
                safe_collection_chain_label(contract, collection_id),
                "green",
            ),
            ("token_id", args.token_id, "cyan"),
            ("has_voted", has_voted, "green" if has_voted else "red"),
            ("choice", choice, "green" if choice else "yellow"),
            (
                "choice_label",
                safe_choice_label(contract, choice) if choice else "",
                "green",
            ),
            ("voting_power", voting_power, "yellow" if voting_power else "cyan"),
            ("voter", voter, "cyan"),
            (
                "pending_request_id",
                pending_request_id,
                "yellow" if pending_request_id else "green",
            ),
            (
                "contract_balance",
                f"{web3.from_wei(balance, 'ether')} {config.network.native_symbol}",
                "green" if balance > 0 else "yellow",
            ),
        ],
        border_style="green" if has_voted else "yellow",
    )


def read_vote_count(web3: Web3, config: AppConfig, args: argparse.Namespace) -> None:
    contract = vote_contract(web3, config, args.contract_address)
    count = contract.functions.getChoiceCount(args.choice).call()
    print_kv_panel(
        "Weighted Choice Count",
        [
            ("vote_contract_address", contract.address, "cyan"),
            ("choice", args.choice, "cyan"),
            ("choice_label", safe_choice_label(contract, args.choice), "green"),
            ("weighted_count", count, "green" if count > 0 else "yellow"),
        ],
        border_style="green" if count > 0 else "yellow",
    )


def read_poll_info(web3: Web3, config: AppConfig, args: argparse.Namespace) -> None:
    contract = vote_contract(web3, config, args.contract_address)
    max_choice = contract.functions.maxChoice().call()
    max_collection_id = safe_max_collection_id(contract)
    rows: list[tuple[str, Any, Optional[str]]] = [
        ("vote_contract_address", contract.address, "cyan"),
        ("poll_question", contract.functions.pollQuestion().call(), "green"),
        ("max_choice", max_choice, "cyan"),
        ("max_collection_id", max_collection_id, "cyan"),
    ]
    for choice in range(1, max_choice + 1):
        rows.append((f"choice_{choice}", safe_choice_label(contract, choice), "green"))
    print_kv_panel("Poll Info", rows, border_style="green")


def read_collections(web3: Web3, config: AppConfig, args: argparse.Namespace) -> None:
    contract = vote_contract(web3, config, args.contract_address)
    collection_ids = safe_supported_collection_ids(contract)
    table = Table(title="Supported Voting Collections")
    table.add_column("Collection ID", style="cyan")
    table.add_column("Label", style="green")
    table.add_column("Display", style="green")
    table.add_column("Chain", style="cyan")
    table.add_column("Voting Power", justify="right", style="yellow")
    for collection_id in collection_ids:
        table.add_row(
            str(collection_id),
            safe_collection_label(contract, collection_id),
            safe_collection_display_label(contract, collection_id),
            safe_collection_chain_label(contract, collection_id),
            str(safe_collection_voting_power(contract, collection_id)),
        )
    CONSOLE.print(table)


def read_results(web3: Web3, config: AppConfig, args: argparse.Namespace) -> None:
    contract = vote_contract(web3, config, args.contract_address)
    counts = contract.functions.getAllChoiceCounts().call()
    leader_choice, leader_votes, has_votes, is_tie = (
        contract.functions.leadingChoice().call()
    )

    table = Table(title="Weighted Poll Results")
    table.add_column("Choice", style="cyan")
    table.add_column("Label", style="green")
    table.add_column("Weighted Votes", justify="right")
    for index, count in enumerate(counts, start=1):
        table.add_row(str(index), safe_choice_label(contract, index), str(count))
    CONSOLE.print(table)

    if not has_votes:
        leader_summary = "No votes yet"
        leader_style = "yellow"
    elif is_tie:
        leader_summary = f"Tie at {leader_votes} weighted votes"
        leader_style = "yellow"
    else:
        leader_summary = (
            f"{leader_choice} - {safe_choice_label(contract, leader_choice)} "
            f"with {leader_votes} weighted votes"
        )
        leader_style = "green"
    print_kv_panel(
        "Leader",
        [
            ("vote_contract_address", contract.address, "cyan"),
            ("has_votes", has_votes, "green" if has_votes else "yellow"),
            ("is_tie", is_tie, "yellow" if is_tie else "green"),
            ("leader", leader_summary, leader_style),
        ],
        border_style=leader_style,
    )


def read_pending_vote(web3: Web3, config: AppConfig, args: argparse.Namespace) -> None:
    contract = vote_contract(web3, config, args.contract_address)
    pending = contract.functions.pendingVotes(args.request_id).call()
    collection_id = int(pending[2])
    print_kv_panel(
        "Pending Vote",
        [
            ("vote_contract_address", contract.address, "cyan"),
            ("request_id", args.request_id, "cyan"),
            ("exists", pending[0], "yellow" if pending[0] else "green"),
            ("voter", pending[1], "cyan"),
            ("collection_id", collection_id, "cyan"),
            (
                "collection_label",
                safe_collection_label(contract, collection_id) if pending[0] else "",
                "green",
            ),
            (
                "target_chain",
                (
                    safe_collection_chain_label(contract, collection_id)
                    if pending[0]
                    else ""
                ),
                "green",
            ),
            ("token_id", pending[3], "cyan"),
            ("choice", pending[4], "green" if pending[4] else "yellow"),
            (
                "choice_label",
                safe_choice_label(contract, pending[4]) if pending[4] else "",
                "green",
            ),
            ("created_at", pending[5], "cyan"),
        ],
        border_style="yellow" if pending[0] else "green",
    )


def set_base_url(web3: Web3, config: AppConfig, args: argparse.Namespace) -> None:
    assert_valid_base_ownership_url(args.url)
    contract = vote_contract(web3, config, args.contract_address)
    sign_send_wait(
        web3, config, contract.functions.setBaseOwnershipUrl(args.url), "set-url"
    )


def withdraw(web3: Web3, config: AppConfig, args: argparse.Namespace) -> None:
    contract = vote_contract(web3, config, args.contract_address)
    recipient = Web3.to_checksum_address(args.to)
    amount_wei = tokens_to_wei(args.amount_stt)
    sign_send_wait(
        web3,
        config,
        contract.functions.withdraw(recipient, amount_wei),
        "withdraw",
    )


def set_agent_config(web3: Web3, config: AppConfig, args: argparse.Namespace) -> None:
    contract = vote_contract(web3, config, args.contract_address)
    selector = require_bytes4(args.json_api_method_selector)
    price_wei = tokens_to_wei(args.agent_price_per_validator_stt)
    assert_live_agent_settings(
        json_api_agent_id=args.json_api_agent_id,
        json_api_method_selector=selector,
        ownership_response_kind=args.ownership_response_kind,
        base_ownership_url=contract.functions.baseOwnershipUrl().call(),
        agent_price_per_validator_wei=price_wei,
    )
    sign_send_wait(
        web3,
        config,
        contract.functions.setAgentConfig(
            args.json_api_agent_id,
            selector,
            price_wei,
            args.agent_subcommittee_size,
            OWNERSHIP_RESPONSE_KINDS[args.ownership_response_kind],
        ),
        "set-agent-config",
    )


def set_reward(web3: Web3, config: AppConfig, args: argparse.Namespace) -> None:
    contract = vote_contract(web3, config, args.contract_address)
    sign_send_wait(
        web3,
        config,
        contract.functions.setRewardWei(tokens_to_wei(args.reward_stt)),
        "set-reward",
    )


def set_pending_timeout(
    web3: Web3, config: AppConfig, args: argparse.Namespace
) -> None:
    assert args.seconds > 0, "seconds must be positive"
    contract = vote_contract(web3, config, args.contract_address)
    sign_send_wait(
        web3,
        config,
        contract.functions.setPendingRequestTimeoutSeconds(args.seconds),
        "set-pending-timeout",
    )


def release_expired_pending_vote(
    web3: Web3,
    config: AppConfig,
    args: argparse.Namespace,
) -> None:
    contract = vote_contract(web3, config, args.contract_address)
    sign_send_wait(
        web3,
        config,
        contract.functions.releaseExpiredPendingVote(args.request_id),
        "release-expired",
    )


def pause_contract(web3: Web3, config: AppConfig, args: argparse.Namespace) -> None:
    contract = vote_contract(web3, config, args.contract_address)
    sign_send_wait(web3, config, contract.functions.pause(), "pause")


def unpause_contract(web3: Web3, config: AppConfig, args: argparse.Namespace) -> None:
    contract = vote_contract(web3, config, args.contract_address)
    sign_send_wait(web3, config, contract.functions.unpause(), "unpause")


def transfer_ownership(web3: Web3, config: AppConfig, args: argparse.Namespace) -> None:
    contract = vote_contract(web3, config, args.contract_address)
    sign_send_wait(
        web3,
        config,
        contract.functions.transferOwnership(Web3.to_checksum_address(args.new_owner)),
        "transfer-ownership",
    )


def debug_void_vote(web3: Web3, config: AppConfig, args: argparse.Namespace) -> None:
    contract = vote_contract(web3, config, args.contract_address)
    collection_id = resolve_collection_id(args)
    require_debug_admin(contract, config)
    previous_choice = contract.functions.getTokenVote(
        collection_id,
        args.token_id,
    ).call()
    previous_voter = contract.functions.tokenVoter(collection_id, args.token_id).call()
    previous_weight = contract.functions.tokenVotingPower(
        collection_id,
        args.token_id,
    ).call()
    print_kv_panel(
        "DEBUG / DEMO ONLY: Void Vote",
        [
            ("vote_contract_address", contract.address, "cyan"),
            ("from_address", config.wallet_address, "cyan"),
            ("collection_id", collection_id, "cyan"),
            (
                "collection_label",
                safe_collection_label(contract, collection_id),
                "green",
            ),
            ("token_id", args.token_id, "cyan"),
            ("previous_choice", previous_choice, "yellow"),
            (
                "previous_choice_label",
                safe_choice_label(contract, previous_choice) if previous_choice else "",
                "yellow",
            ),
            ("previous_weight", previous_weight, "yellow"),
            ("previous_voter", previous_voter, "cyan"),
            ("dry_run", args.dry_run, "yellow" if args.dry_run else "red"),
        ],
        border_style="yellow",
    )
    if args.dry_run:
        return
    sign_send_wait(
        web3,
        config,
        contract.functions.debugOnlyVoidVote(collection_id, args.token_id),
        "debug-void-vote",
    )


def debug_cancel_pending(
    web3: Web3, config: AppConfig, args: argparse.Namespace
) -> None:
    contract = vote_contract(web3, config, args.contract_address)
    require_debug_admin(contract, config)
    pending = contract.functions.pendingVotes(args.request_id).call()
    collection_id = int(pending[2])
    print_kv_panel(
        "DEBUG / DEMO ONLY: Cancel Pending Request",
        [
            ("vote_contract_address", contract.address, "cyan"),
            ("from_address", config.wallet_address, "cyan"),
            ("request_id", args.request_id, "cyan"),
            ("exists", pending[0], "yellow" if pending[0] else "red"),
            ("voter", pending[1], "cyan"),
            ("collection_id", collection_id, "cyan"),
            (
                "collection_label",
                safe_collection_label(contract, collection_id) if pending[0] else "",
                "green",
            ),
            ("token_id", pending[3], "cyan"),
            ("choice", pending[4], "yellow"),
            (
                "choice_label",
                safe_choice_label(contract, pending[4]) if pending[4] else "",
                "yellow",
            ),
            ("dry_run", args.dry_run, "yellow" if args.dry_run else "red"),
        ],
        border_style="yellow",
    )
    if args.dry_run:
        return
    sign_send_wait(
        web3,
        config,
        contract.functions.debugOnlyCancelPendingRequest(args.request_id),
        "debug-cancel-pending",
    )


def debug_withdraw_stt(web3: Web3, config: AppConfig, args: argparse.Namespace) -> None:
    contract = vote_contract(web3, config, args.contract_address)
    require_debug_admin(contract, config)
    recipient = Web3.to_checksum_address(args.to)
    amount_wei = tokens_to_wei(args.amount_stt)
    print_debug_withdraw_panel(
        web3, config, contract, recipient, amount_wei, args.dry_run
    )
    if args.dry_run:
        return
    sign_send_wait(
        web3,
        config,
        contract.functions.debugOnlyWithdrawSTT(recipient, amount_wei),
        "debug-withdraw-stt",
    )


def debug_withdraw_all_stt(
    web3: Web3, config: AppConfig, args: argparse.Namespace
) -> None:
    contract = vote_contract(web3, config, args.contract_address)
    require_debug_admin(contract, config)
    recipient = Web3.to_checksum_address(args.to)
    amount_wei = web3.eth.get_balance(contract.address)
    print_debug_withdraw_panel(
        web3, config, contract, recipient, amount_wei, args.dry_run
    )
    if args.dry_run:
        return
    sign_send_wait(
        web3,
        config,
        contract.functions.debugOnlyWithdrawAllSTT(recipient),
        "debug-withdraw-all-stt",
    )


def print_debug_withdraw_panel(
    web3: Web3,
    config: AppConfig,
    contract: Any,
    recipient: str,
    amount_wei: int,
    dry_run: bool,
) -> None:
    balance_wei = web3.eth.get_balance(contract.address)
    print_kv_panel(
        "DEBUG / DEMO ONLY: Withdraw STT",
        [
            ("vote_contract_address", contract.address, "cyan"),
            ("from_address", config.wallet_address, "cyan"),
            ("to", recipient, "cyan"),
            (
                "amount",
                f"{wei_to_token(amount_wei)} {config.network.native_symbol}",
                "yellow",
            ),
            (
                "contract_balance",
                f"{wei_to_token(balance_wei)} {config.network.native_symbol}",
                "green" if balance_wei >= amount_wei else "red",
            ),
            ("dry_run", dry_run, "yellow" if dry_run else "red"),
        ],
        border_style="yellow",
    )


def require_debug_admin(contract: Any, config: AppConfig) -> str:
    debug_admin = Web3.to_checksum_address(contract.functions.debugAdmin().call())
    signer = Web3.to_checksum_address(config.wallet_address)
    print_kv_panel(
        "Debug Admin Check",
        [
            ("debug_admin", debug_admin, "cyan"),
            ("from_address", signer, "cyan"),
            (
                "authorized",
                signer == debug_admin,
                "green" if signer == debug_admin else "red",
            ),
        ],
        border_style="green" if signer == debug_admin else "red",
    )
    assert signer == debug_admin, "signer is not debugAdmin"
    return debug_admin


def resolve_deploy_platform(
    config: AppConfig,
    args: argparse.Namespace,
) -> tuple[str, bool]:
    selected = [
        args.platform_address is not None,
        args.use_mock_platform,
        args.use_config_platform,
    ]
    assert sum(1 for value in selected if value) == 1, (
        "Choose exactly one deploy target: --platform-address, "
        "--use-mock-platform, or --use-config-platform"
    )
    if args.platform_address is not None:
        return Web3.to_checksum_address(args.platform_address), False
    if args.use_mock_platform:
        assert (
            config.mock_platform_address
        ), "mock_platform_address is required in config for --use-mock-platform"
        return Web3.to_checksum_address(config.mock_platform_address), True
    return Web3.to_checksum_address(config.platform_contract), False


def resolve_probe_platform(config: AppConfig, args: argparse.Namespace) -> str:
    selected = [
        args.platform_address is not None,
        args.use_config_platform,
    ]
    assert (
        sum(1 for value in selected if value) == 1
    ), "Choose exactly one probe target: --platform-address or --use-config-platform"
    if args.platform_address is not None:
        return Web3.to_checksum_address(args.platform_address)
    return Web3.to_checksum_address(config.platform_contract)


def print_vote_dry_run(
    web3: Web3,
    config: AppConfig,
    contract: Any,
    args: argparse.Namespace,
    collection_id: int,
) -> None:
    url = contract.functions.ownershipUrl(
        collection_id,
        config.wallet_address,
        args.token_id,
    ).call()
    selector_path = contract.functions.ownershipSelectorPath().call()
    method_selector = bytes4_to_hex(contract.functions.jsonApiMethodSelector().call())
    payload = contract.functions.jsonApiPayload(
        collection_id,
        config.wallet_address,
        args.token_id,
    ).call()
    request_value_wei = contract.functions.quoteRequestValueWei().call()
    reward_wei = contract.functions.rewardWei().call()
    contract_balance_wei = web3.eth.get_balance(contract.address)
    balance_status = build_vote_balance_status(
        contract_balance_wei,
        request_value_wei,
        reward_wei,
    )
    agent_platform = Web3.to_checksum_address(contract.functions.agentPlatform().call())
    is_mock_platform = is_configured_mock_platform(config, agent_platform)
    response_kind_id = contract.functions.ownershipResponseKind().call()
    result = {
        "choice": args.choice,
        "collection_id": collection_id,
        "token_id": args.token_id,
        "from_address": config.wallet_address,
        "contract_address": contract.address,
        "agent_platform": agent_platform,
        "is_configured_mock_platform": is_mock_platform,
        "json_api_agent_id": contract.functions.jsonApiAgentId().call(),
        "method_selector": method_selector,
        "selector_path": selector_path,
        "ownership_response_kind": response_kind_name(response_kind_id),
        "url": url,
        "payload_hex": Web3.to_hex(payload),
        "request_value_wei": request_value_wei,
        "request_value_stt": str(wei_to_token(request_value_wei)),
        "reward_stt": str(wei_to_token(reward_wei)),
        "contract_balance_wei": contract_balance_wei,
        "contract_balance_stt": str(wei_to_token(contract_balance_wei)),
        "balance_sufficient": balance_status["balance_sufficient"],
        "balance_warn_for_successful_vote": balance_status[
            "balance_warn_for_successful_vote"
        ],
        "estimated_remaining_requests": balance_status["estimated_remaining_requests"],
        "estimated_successful_votes": balance_status["estimated_successful_votes"],
    }
    print_kv_panel(
        "Vote Dry Run",
        [
            ("vote_contract_address", contract.address, "cyan"),
            ("from_address", config.wallet_address, "cyan"),
            ("collection_id", collection_id, "cyan"),
            (
                "collection_label",
                safe_collection_label(contract, collection_id),
                "green",
            ),
            (
                "target_chain",
                safe_collection_chain_label(contract, collection_id),
                "green",
            ),
            (
                "voting_power",
                safe_collection_voting_power(contract, collection_id),
                "yellow",
            ),
            ("token_id", args.token_id, "cyan"),
            ("choice", args.choice, "green"),
            ("choice_label", safe_choice_label(contract, args.choice), "green"),
            ("agent_platform", agent_platform, "cyan"),
            (
                "is_configured_mock_platform",
                is_mock_platform,
                "green" if is_mock_platform else "yellow",
            ),
            ("json_api_agent_id", result["json_api_agent_id"], "cyan"),
            ("method_selector", method_selector, "cyan"),
            ("selector_path", selector_path, "green"),
            ("ownership_response_kind", result["ownership_response_kind"], "green"),
            ("url", url, "blue"),
            ("request_value_stt", result["request_value_stt"], "yellow"),
            ("reward_stt", result["reward_stt"], "yellow"),
            (
                "contract_balance_stt",
                result["contract_balance_stt"],
                "green" if balance_status["balance_sufficient"] else "red",
            ),
            (
                "balance_sufficient",
                result["balance_sufficient"],
                "green" if result["balance_sufficient"] else "red",
            ),
            (
                "balance_warn_for_successful_vote",
                result["balance_warn_for_successful_vote"],
                "yellow" if result["balance_warn_for_successful_vote"] else "green",
            ),
            (
                "estimated_remaining_requests",
                result["estimated_remaining_requests"],
                "cyan",
            ),
            (
                "estimated_successful_votes",
                result["estimated_successful_votes"],
                "cyan",
            ),
            ("payload_hex", result["payload_hex"], None),
        ],
        border_style="yellow",
    )


def assert_contract_is_ready_for_spendful_vote(
    config: AppConfig, contract: Any
) -> None:
    agent_platform = Web3.to_checksum_address(contract.functions.agentPlatform().call())
    if is_configured_mock_platform(config, agent_platform):
        return

    assert_live_agent_settings(
        json_api_agent_id=contract.functions.jsonApiAgentId().call(),
        json_api_method_selector=bytes4_to_hex(
            contract.functions.jsonApiMethodSelector().call()
        ),
        ownership_response_kind=response_kind_name(
            contract.functions.ownershipResponseKind().call()
        ),
        base_ownership_url=contract.functions.baseOwnershipUrl().call(),
        agent_price_per_validator_wei=contract.functions.agentPricePerValidatorWei().call(),
    )


def build_vote_balance_status(
    contract_balance_wei: int,
    request_value_wei: int,
    reward_wei: int = 0,
) -> dict[str, Any]:
    estimated_remaining_requests = (
        None if request_value_wei == 0 else contract_balance_wei // request_value_wei
    )
    accepted_vote_cost_wei = request_value_wei + reward_wei
    estimated_successful_votes = (
        None
        if accepted_vote_cost_wei == 0
        else contract_balance_wei // accepted_vote_cost_wei
    )
    return {
        "balance_sufficient": contract_balance_wei >= request_value_wei,
        "balance_warn_for_successful_vote": contract_balance_wei
        < accepted_vote_cost_wei,
        "estimated_remaining_requests": estimated_remaining_requests,
        "estimated_successful_votes": estimated_successful_votes,
        "accepted_vote_cost_wei": accepted_vote_cost_wei,
    }


def assert_vote_contract_balance_sufficient(
    web3: Web3,
    config: AppConfig,
    contract: Any,
    request_value_wei: int,
    reward_wei: int = 0,
    config_path: Any = "config.local.json",
) -> None:
    contract_balance_wei = web3.eth.get_balance(contract.address)
    if contract_balance_wei < request_value_wei:
        raise AssertionError(
            "Vote contract balance is too low for the JSON API request.\n"
            "vote() is not payable; the JSON API request value is paid from the "
            "vote contract balance.\n"
            f"contract_balance={wei_to_token(contract_balance_wei)} "
            f"{config.network.native_symbol}; "
            f"request_value={wei_to_token(request_value_wei)} "
            f"{config.network.native_symbol}\n"
            "Fund the contract first with:\n\n"
            'VOTE_CONTRACT_ADDRESS="' + contract.address + '"\n'
            "python scripts/somnia_vote_cli.py --config "
            f"{shlex.quote(str(config_path))} fund \\\n"
            '  --contract-address "$VOTE_CONTRACT_ADDRESS" \\\n'
            "  --amount-stt 1"
        )

    accepted_vote_cost_wei = request_value_wei + reward_wei
    if accepted_vote_cost_wei and contract_balance_wei < accepted_vote_cost_wei:
        LOGGER.warning(
            "[yellow]contract balance covers the request but may not cover a "
            "successful vote reward. balance=%s %s request_plus_reward=%s %s[/]",
            wei_to_token(contract_balance_wei),
            config.network.native_symbol,
            wei_to_token(accepted_vote_cost_wei),
            config.network.native_symbol,
        )


def assert_live_agent_settings(
    json_api_agent_id: int,
    json_api_method_selector: str,
    ownership_response_kind: str,
    base_ownership_url: str,
    agent_price_per_validator_wei: int,
    allow_example_url: bool = False,
) -> None:
    ownership_response_kind = require_response_kind(ownership_response_kind)
    assert json_api_agent_id != 0, "live JSON API agent ID is still placeholder 0"
    assert (
        require_bytes4(json_api_method_selector) != ZERO_BYTES4
    ), "live JSON API method selector is still placeholder 0x00000000"
    if ownership_response_kind == "uint":
        assert (
            require_bytes4(json_api_method_selector)
            == DEFAULT_JSON_API_FETCH_UINT_SELECTOR
        ), (
            "uint live mode must use documented fetchUint(string,string,uint8) "
            f"selector {DEFAULT_JSON_API_FETCH_UINT_SELECTOR}"
        )
    else:
        raise AssertionError(
            "bool live mode is not sufficiently documented; use uint/votingPower mode"
        )
    if not allow_example_url:
        assert (
            "example.com" not in base_ownership_url.lower()
        ), "base ownership URL still points at an example domain"
        assert (
            "wrapper.example" not in base_ownership_url.lower()
        ), "base ownership URL still points at wrapper.example"
    assert (
        agent_price_per_validator_wei > 0
    ), "agent price per validator must be confirmed before live use"


def assert_valid_base_ownership_url(base_ownership_url: str) -> None:
    assert base_ownership_url, "base ownership URL is required"
    assert base_ownership_url.startswith(
        ("http://", "https://")
    ), "base ownership URL must start with http:// or https://"
    assert "?" not in base_ownership_url, (
        "base ownership URL must not include a query string; "
        "the contract appends ?collectionId=...&wallet=...&tokenId=..."
    )


def assert_valid_probe_url(url: str) -> None:
    assert url, "probe URL is required"
    assert url.startswith(("http://", "https://")), "probe URL must be HTTP(S)"


def is_configured_mock_platform(config: AppConfig, platform_address: str) -> bool:
    return config.mock_platform_address is not None and Web3.to_checksum_address(
        config.mock_platform_address
    ) == Web3.to_checksum_address(platform_address)


def vote_contract(
    web3: Web3,
    config: AppConfig,
    address_override: Optional[str],
) -> Any:
    address = resolve_contract_address(config, address_override)
    abi, _ = get_contract_interface(
        compile_contracts(config.solc_binary),
        "contracts/NftGatedVote.sol",
        "NftGatedVote",
    )
    return web3.eth.contract(address=address, abi=abi)


def probe_contract(
    web3: Web3,
    config: AppConfig,
    address_override: Optional[str],
) -> Any:
    address = address_override or config.probe_contract_address
    assert address, "Need --probe-contract-address or probe_contract_address in config"
    abi, _ = get_contract_interface(
        compile_contracts(config.solc_binary),
        "contracts/JsonApiUintProbe.sol",
        "JsonApiUintProbe",
    )
    return web3.eth.contract(address=Web3.to_checksum_address(address), abi=abi)


def resolve_contract_address(
    config: AppConfig,
    address_override: Optional[str],
) -> str:
    address = address_override or config.vote_contract_address
    assert address, "Need --contract-address or vote_contract_address in config"
    return Web3.to_checksum_address(address)


def sign_send_wait(
    web3: Web3,
    config: AppConfig,
    tx_or_function: Any,
    label: str,
    value_wei: int = 0,
) -> dict[str, Any]:
    assert web3.is_connected(), f"Could not connect to RPC: {config.rpc_url}"
    assert web3.eth.chain_id == config.network.chain_id, "RPC chain ID mismatch"

    base_tx = {
        "chainId": config.network.chain_id,
        "from": config.wallet_address,
        "nonce": web3.eth.get_transaction_count(config.wallet_address),
        "gasPrice": resolve_gas_price(web3, config),
    }
    if value_wei:
        base_tx["value"] = value_wei

    if hasattr(tx_or_function, "build_transaction"):
        try:
            estimate_tx = {"from": config.wallet_address}
            if value_wei:
                estimate_tx["value"] = value_wei
            estimated_gas = tx_or_function.estimate_gas(estimate_tx)
            base_tx["gas"] = int(Decimal(estimated_gas) * Decimal("1.25"))
        except Exception as exc:
            LOGGER.warning("gas estimation failed; using fallback. error=%s", exc)
            base_tx["gas"] = config.gas_limit
        tx = tx_or_function.build_transaction(base_tx)
    else:
        tx = {**base_tx, **tx_or_function, "gas": config.gas_limit}

    assert_balance_covers_tx(web3, config, tx)
    signed = web3.eth.account.sign_transaction(tx, private_key=config.private_key)
    raw_tx = getattr(signed, "raw_transaction", None) or getattr(
        signed, "rawTransaction"
    )

    LOGGER.info("[cyan]submitting=%s[/]", label)
    tx_hash = web3.eth.send_raw_transaction(raw_tx)
    tx_hash_hex = web3.to_hex(tx_hash)
    LOGGER.info("[cyan]tx_hash=%s[/]", tx_hash_hex)
    LOGGER.info(
        "[blue]explorer_url=%s/tx/%s[/]",
        config.network.explorer_url.rstrip("/"),
        tx_hash_hex,
    )
    receipt = web3.eth.wait_for_transaction_receipt(tx_hash, timeout=180)
    assert receipt["status"] == 1, f"Transaction reverted: {label}"
    LOGGER.info(
        "[green]block_number=%s gas_used=%s[/]",
        receipt["blockNumber"],
        receipt["gasUsed"],
    )
    return receipt


def resolve_gas_price(web3: Web3, config: AppConfig) -> int:
    if config.gas_price_gwei is not None:
        return int(config.gas_price_gwei * Decimal(10) ** 9)
    return int(web3.eth.gas_price)


def assert_balance_covers_tx(web3: Web3, config: AppConfig, tx: dict[str, Any]) -> None:
    value = int(tx.get("value", 0))
    needed = int(tx["gas"]) * int(tx["gasPrice"]) + value
    balance = web3.eth.get_balance(config.wallet_address)
    assert balance >= needed, (
        f"Insufficient balance: need about {web3.from_wei(needed, 'ether')} "
        f"{config.network.native_symbol}, have {web3.from_wei(balance, 'ether')} "
        f"{config.network.native_symbol}"
    )


def require_str(raw: dict[str, Any], key: str, default: str) -> str:
    value = raw.get(key, default)
    assert isinstance(value, str), f"{key} must be a string"
    return value


def require_int(
    raw: dict[str, Any],
    key: str,
    default: int,
    minimum: Optional[int] = None,
    maximum: Optional[int] = None,
) -> int:
    value = raw.get(key, default)
    assert isinstance(value, int), f"{key} must be an integer"
    if minimum is not None:
        assert value >= minimum, f"{key} must be >= {minimum}"
    if maximum is not None:
        assert value <= maximum, f"{key} must be <= {maximum}"
    return value


def require_bytes4(value: Any) -> str:
    assert isinstance(value, str), "bytes4 value must be a string"
    assert (
        value.startswith("0x") and len(value) == 10
    ), "bytes4 value must look like 0x12345678"
    int(value[2:], 16)
    return value


def require_response_kind(value: Any) -> str:
    assert isinstance(value, str), "ownership_response_kind must be a string"
    normalized = value.lower()
    assert (
        normalized in OWNERSHIP_RESPONSE_KINDS
    ), "ownership_response_kind must be 'uint' or 'bool'"
    return normalized


def response_kind_name(value: int) -> str:
    for name, numeric_value in OWNERSHIP_RESPONSE_KINDS.items():
        if numeric_value == value:
            return name
    return f"unknown:{value}"


def resolve_collection_id(args: argparse.Namespace) -> int:
    if getattr(args, "collection_id", None) is not None:
        collection_id = int(args.collection_id)
    else:
        collection_name = getattr(args, "collection", None)
        assert collection_name in COLLECTION_ALIASES, "collection is required"
        collection_id = COLLECTION_ALIASES[collection_name]
    assert 0 <= collection_id <= 255, "collection ID must fit uint8"
    return collection_id


def default_collection_label(collection_id: int) -> str:
    return str(
        DEFAULT_COLLECTIONS.get(collection_id, {}).get(
            "label",
            f"collection-{collection_id}",
        )
    )


def default_collection_display_label(collection_id: int) -> str:
    return str(
        DEFAULT_COLLECTIONS.get(collection_id, {}).get(
            "display_label",
            default_collection_label(collection_id),
        )
    )


def default_collection_chain_label(collection_id: int) -> str:
    return str(
        DEFAULT_COLLECTIONS.get(collection_id, {}).get(
            "chain",
            "unknown",
        )
    )


def default_collection_voting_power(collection_id: int) -> int:
    return int(DEFAULT_COLLECTIONS.get(collection_id, {}).get("voting_power", 0))


def safe_collection_label(contract: Any, collection_id: int) -> str:
    try:
        value = contract.functions.collectionLabel(collection_id).call()
        return value or default_collection_label(collection_id)
    except Exception:
        return default_collection_label(collection_id)


def safe_collection_display_label(contract: Any, collection_id: int) -> str:
    try:
        value = contract.functions.collectionDisplayLabel(collection_id).call()
        return value or default_collection_display_label(collection_id)
    except Exception:
        return default_collection_display_label(collection_id)


def safe_collection_chain_label(contract: Any, collection_id: int) -> str:
    try:
        value = contract.functions.collectionChainLabel(collection_id).call()
        return value or default_collection_chain_label(collection_id)
    except Exception:
        return default_collection_chain_label(collection_id)


def safe_collection_voting_power(contract: Any, collection_id: int) -> int:
    try:
        return int(contract.functions.collectionVotingPower(collection_id).call())
    except Exception:
        return default_collection_voting_power(collection_id)


def safe_max_collection_id(contract: Any) -> int:
    try:
        return int(contract.functions.maxCollectionId().call())
    except Exception:
        return max(DEFAULT_COLLECTIONS)


def safe_supported_collection_ids(contract: Any) -> list[int]:
    try:
        return [
            int(value) for value in contract.functions.supportedCollectionIds().call()
        ]
    except Exception:
        return sorted(DEFAULT_COLLECTIONS)


def safe_choice_label(contract: Any, choice: int) -> str:
    if not choice:
        return ""
    try:
        return contract.functions.choiceLabel(choice).call()
    except Exception:
        return ""


def print_live_defaults() -> None:
    result = {
        "platform_contract": NETWORKS["testnet"].platform_contract,
        "json_api_agent_id": DEFAULT_JSON_API_AGENT_ID,
        "json_api_method_signature": DEFAULT_JSON_API_FETCH_UINT_SIGNATURE,
        "json_api_method_selector": DEFAULT_JSON_API_FETCH_UINT_SELECTOR,
        "ownership_response_kind": "uint",
        "selector_path": OWNERSHIP_UINT_SELECTOR,
        "decimals": OWNERSHIP_UINT_DECIMALS,
        "agent_price_per_validator_stt": DEFAULT_JSON_API_PRICE_PER_VALIDATOR_STT,
        "agent_subcommittee_size": DEFAULT_JSON_API_SUBCOMMITTEE_SIZE,
        "request_value_formula": "getRequestDeposit() + price_per_validator * subcommittee_size",
        "estimated_json_api_request_value_stt": "0.12",
    }
    print_kv_panel(
        "Live JSON API Defaults",
        [
            ("platform_contract", result["platform_contract"], "cyan"),
            ("json_api_agent_id", result["json_api_agent_id"], "cyan"),
            ("json_api_method_signature", result["json_api_method_signature"], "green"),
            ("json_api_method_selector", result["json_api_method_selector"], "cyan"),
            ("ownership_response_kind", result["ownership_response_kind"], "green"),
            ("selector_path", result["selector_path"], "green"),
            ("decimals", result["decimals"], "green"),
            (
                "agent_price_per_validator_stt",
                result["agent_price_per_validator_stt"],
                "yellow",
            ),
            ("agent_subcommittee_size", result["agent_subcommittee_size"], "yellow"),
            ("request_value_formula", result["request_value_formula"], None),
            (
                "estimated_json_api_request_value_stt",
                result["estimated_json_api_request_value_stt"],
                "yellow",
            ),
        ],
        border_style="green",
    )


def bytes4_to_hex(value: Any) -> str:
    if isinstance(value, str):
        return require_bytes4(value)
    if isinstance(value, (bytes, bytearray)):
        assert len(value) == 4, "bytes4 value must have length 4"
        return "0x" + bytes(value).hex()
    assert False, f"Unsupported bytes4 value type: {type(value).__name__}"


def optional_address(value: Any) -> Optional[str]:
    if value in (None, ""):
        return None
    assert isinstance(value, str), "address must be a string"
    return Web3.to_checksum_address(value)


def optional_decimal(value: Any) -> Optional[Decimal]:
    if value in (None, ""):
        return None
    return Decimal(str(value))


def tokens_to_wei(value: str | Decimal) -> int:
    return int(Decimal(str(value)) * TOKEN_WEI)


def wei_to_token(value_wei: int) -> Decimal:
    return Decimal(value_wei) / TOKEN_WEI


if __name__ == "__main__":
    main()
