# AI Poll Demo Contract Deployment

Date: 2026-05-27

Historical note: this file preserves deployment evidence for an earlier AI poll
iteration. The current public weighted vote contract is
`0x919eD02eba4772a72d6C75430026709009858754`; use the root `README.md` and
`docs/live_runbook.md` for current demo configuration.

## Contract

```text
network=Somnia Shannon testnet
vote_contract_address=0xB4f7De2f52c0cd0B9A1Bd1e505C8ce53799a2691
deploy_tx=0x1260e2f9c78e5c19fdeaea811b60efa90d29136005d45a8b7d70ee93c2e69b90
platform_contract=0x037Bb9C718F3f7fe5eCBDB0b600D607b52706776
base_url=https://somnia-ownership-wrapper-735868209397.europe-west1.run.app/owns
json_api_agent_id=13174292974160097713
json_api_method_selector=0x3bbc1302
ownership_response_kind=uint
selector_path=ownsInt
decimals=0
agent_price_per_validator_stt=0.03
agent_subcommittee_size=3
request_value_stt=0.12
reward_stt=0.01
max_choice=3
```

Explorer:
https://shannon-explorer.somnia.network/tx/0x1260e2f9c78e5c19fdeaea811b60efa90d29136005d45a8b7d70ee93c2e69b90

## Poll Metadata

```text
Question: Which AI assistant should lead the next agentic workflow?
Choice 1: ChatGPT
Choice 2: Claude
Choice 3: DeepSeek
```

Read-only verification:

```bash
VOTE_CONTRACT_ADDRESS="0xB4f7De2f52c0cd0B9A1Bd1e505C8ce53799a2691"

python scripts/somnia_vote_cli.py --config config.local.json poll-info \
  --contract-address "$VOTE_CONTRACT_ADDRESS"

python scripts/somnia_vote_cli.py --config config.local.json results \
  --contract-address "$VOTE_CONTRACT_ADDRESS"
```

Initial result state:

```text
choice_1=0
choice_2=0
choice_3=0
has_votes=False
is_tie=False
leader=No votes yet
```

## Operational Notes

- This is the next demo contract for the AI poll iteration.
- The previous `0x64269DBd44eC5b6a2eeA7b80f693283a512a396D` contract remains the
  proven live CLI reference, but it does not include the new AI poll/debug
  helper surface.
- Fund this contract before live voting; `vote()` is not payable and JSON API
  request value is paid from the contract balance.
- The contract includes `DEBUG / DEMO ONLY` admin helpers marked
  `TODO(DEMO-REMOVE)`. Remove those code paths before any production or
  trustless deployment.
