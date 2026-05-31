# Live Runbook

This is the current order of operations after the weighted multi-collection
`votingPower` update.

## Current Implementation Status

Done in the repo:

1. Wrapper returns `owns`, `ownsInt`, and weighted `votingPower`.
2. Voting contract supports numeric ownership mode and live mode rejects the
   under-documented bool path.
3. Voting contract locks a token while an ownership request is pending.
4. Expired pending requests can be released.
5. `JsonApiUintProbe` verified the official JSON API callback path.
6. The live `NftGatedVote` CLI path completed both rejection and acceptance.
7. The reference AI poll contract is deployed and exposes AI poll metadata,
   result helpers, leader/tie state, and demo-only debug/admin helpers.
8. CLI supports `live-defaults`, `deploy-probe`, `probe-request`, `probe-read`,
   `poll-info`, `results`, `set-pending-timeout`, and `release-expired`.
9. Public wrapper checker script exists at `scripts/check_public_wrapper.py`.

## Live Values

```text
platform_contract=0x037Bb9C718F3f7fe5eCBDB0b600D607b52706776
json_api_agent_id=13174292974160097713
json_api_method_selector=0x3bbc1302
json_api_method=fetchUint(string,string,uint8)
ownership_response_kind=uint
selector_path=votingPower
decimals=0
agent_price_per_validator_stt=0.03
agent_subcommittee_size=3
estimated_request_value_stt=0.12
next_demo_reward_stt=1.02
public_website=https://somnia-agent.web.app
```

## AI Poll Theme

```text
Question: Which AI assistant should lead the next agentic workflow?
Choice 1: ChatGPT
Choice 2: Claude
Choice 3: DeepSeek
```

## Voting Collections

```text
collectionId=1
chain=somnia-mainnet
collection=quills-adventure
voting_power=1

collectionId=2
chain=ethereum-mainnet
collection=bored-ape-yacht-club
voting_power=2
```

The voter is the `from_address` derived from the local private key. Use
`<TOKEN_ID>` for the NFT token ID and `VOTE_CONTRACT_ADDRESS` for the deployed
`NftGatedVote` contract.

## Current public wrapper deployment

Deployment report:
[docs/cloud_run_deploy_2026-05-26.md](cloud_run_deploy_2026-05-26.md)

```bash
WRAPPER_URL="https://somnia-ownership-wrapper-735868209397.europe-west1.run.app"
curl -iS "$WRAPPER_URL/health"
curl -iS "$WRAPPER_URL/owns?collectionId=1&wallet=<DEMO_WALLET_ADDRESS>&tokenId=<TOKEN_ID>"
curl -iS "$WRAPPER_URL/owns?collectionId=2&wallet=<DEMO_WALLET_ADDRESS>&tokenId=<TOKEN_ID>"
```

`JsonApiUintProbe` should use selector path `votingPower` and decimals `0`.

## Current JsonApiUintProbe result

Probe report:
[docs/json_api_probe_2026-05-26.md](json_api_probe_2026-05-26.md)

```text
probe_contract=0x535A56B754e705ab251cD89C4Aa43e62c5F27B3F
deploy_tx=0x46b3f29e3ca1f205ac96e32169c7f8e5743f730ee2e44340f8fec09a4a8a744e
probe_request_tx=0xdf9bd33e83e73f2d8e3793c25745d5f9d43789e17b362c617f179459e9396e53
request_id=2278035
request_value=0.12 STT
last_status=2
last_decode_ok=True
last_decoded_uint=1
last_raw_result=0x0000000000000000000000000000000000000000000000000000000000000001
pending=False
```

The official Somnia JSON API agent successfully fetched the Cloud Run wrapper,
selected a numeric JSON field, and returned an ABI-encoded `uint256`. For the
weighted contract, use selector path `votingPower`.

## Historical Live Vote Result

Live vote report:
[docs/live_vote_2026-05-26.md](live_vote_2026-05-26.md)

This is historical evidence for an earlier single-collection live contract, not
the current public AI poll contract.

```text
VOTE_CONTRACT_ADDRESS=0x64269DBd44eC5b6a2eeA7b80f693283a512a396D
deploy_tx=0xcf416ab0fc47de4f651945c47a0e6d801eaa2c2dd1f58daffc52169bf294352f
funding_tx=0xb6f7980132f125791e9c561845a7977381b8e97bf10bccad552c565cde2503c0
negative_request_id=2281123
negative_result=has_voted=False, choice_1_count=0
positive_request_id=2282739
positive_result=has_voted=True, choice=1, choice_1_count=1
remaining_contract_balance=0.299554582 STT
```

Do not use the older vote contract
`0x226D35C06FC61A662fc70bacE371597618DB75F8` for the current live path.

The live end-to-end NFT-gated voting flow works for both rejection and
acceptance: a non-owner token check does not count a vote, and an owner token
check records the vote after the JSON API callback.

## Current Public AI Poll Contract

Deployment report:
[docs/ai_poll_contract_2026-05-27.md](ai_poll_contract_2026-05-27.md)

```text
VOTE_CONTRACT_ADDRESS=0x919eD02eba4772a72d6C75430026709009858754
deploy_tx=0x1260e2f9c78e5c19fdeaea811b60efa90d29136005d45a8b7d70ee93c2e69b90
```

This is the current public weighted AI poll contract used by the website. Old
contract addresses in the historical proof notes are not the primary live path.

## Result Helpers

The next demo contract exposes:

- `pollQuestion()` for the AI poll question.
- `choiceLabel(uint8)` for `ChatGPT`, `Claude`, and `DeepSeek`.
- `collectionLabel(uint8)`, `collectionChainLabel(uint8)`,
  `collectionVotingPower(uint8)`, and `supportedCollectionIds()`.
- `getChoiceCount(uint8)` and `getAllChoiceCounts()` as weighted counts.
- `leadingChoice()` returning `(choice, votes, hasVotes, isTie)`.

If `hasVotes=false`, display no winner. If `isTie=true`, display `Tie` instead
of a unique winner.

## Debug/Admin Helpers

The next demo contract includes `DEBUG / DEMO ONLY` helpers:

- `debugOnlyVoidVote(uint8 collectionId, uint256 tokenId)`
- `debugOnlyCancelPendingRequest(uint256 requestId)`
- `debugOnlyWithdrawSTT(address payable to, uint256 amountWei)`
- `debugOnlyWithdrawAllSTT(address payable to)`

These are not production-trustless. They intentionally give the deployer/admin
centralized powers for repeated hackathon demos and testing. Before any final or
public trustless deployment, remove all `TODO(DEMO-REMOVE)` code paths and
redeploy a clean contract without admin vote-reset, pending-cancel, or
STT-withdrawal powers.

## Next Contract Deployment

Do not deploy from automation unless the live environment is intentionally
configured and the operator is ready to spend STT. The next public demo contract
should use the same wrapper and JSON API settings with selector path
`votingPower` and accepted-vote reward `1.02 STT`:

```bash
python scripts/somnia_vote_cli.py --config config.local.json deploy-vote \
  --platform-address 0x037Bb9C718F3f7fe5eCBDB0b600D607b52706776 \
  --json-api-agent-id 13174292974160097713 \
  --json-api-method-selector 0x3bbc1302 \
  --ownership-response-kind uint \
  --agent-price-per-validator-stt 0.03 \
  --agent-subcommittee-size 3 \
  --base-url https://somnia-ownership-wrapper-735868209397.europe-west1.run.app/owns \
  --reward-stt 1.02 \
  --max-choice 3
```

After deployment:

1. Set `VOTE_CONTRACT_ADDRESS` to the newly printed contract address.
2. Fund the vote contract before public voting. Start with at least `10 STT`
   for demos because successful votes now pay about `1.02 STT` plus the JSON
   API request value from the vote contract balance:

```bash
python scripts/somnia_vote_cli.py --config config.local.json fund \
  --contract-address "$VOTE_CONTRACT_ADDRESS" \
  --amount-stt 10
```

3. Verify poll metadata and zero/expected result state:

```bash
python scripts/somnia_vote_cli.py --config config.local.json poll-info \
  --contract-address "$VOTE_CONTRACT_ADDRESS"
python scripts/somnia_vote_cli.py --config config.local.json results \
  --contract-address "$VOTE_CONTRACT_ADDRESS"
python scripts/somnia_vote_cli.py --config config.local.json collections \
  --contract-address "$VOTE_CONTRACT_ADDRESS"
```

4. Update `frontend/.env.example`, any local frontend `.env`, and deployment
   docs/config references to the new `VOTE_CONTRACT_ADDRESS`.
5. Rebuild the frontend and redeploy Firebase Hosting to
   `https://somnia-agent.web.app`.
6. Run a dry-run vote and confirm `balance_sufficient=true`:

```bash
python scripts/somnia_vote_cli.py --config config.local.json vote \
  --contract-address "$VOTE_CONTRACT_ADDRESS" \
  --collection-id <COLLECTION_ID> \
  --token-id <TOKEN_ID> \
  --choice <CHOICE> \
  --dry-run
```

7. Submit a live vote, then inspect pending/read/count/results:

```bash
python scripts/somnia_vote_cli.py --config config.local.json vote \
  --contract-address "$VOTE_CONTRACT_ADDRESS" \
  --collection-id <COLLECTION_ID> \
  --token-id <TOKEN_ID> \
  --choice <CHOICE>
python scripts/somnia_vote_cli.py --config config.local.json read \
  --contract-address "$VOTE_CONTRACT_ADDRESS" \
  --collection-id <COLLECTION_ID> \
  --token-id <TOKEN_ID>
python scripts/somnia_vote_cli.py --config config.local.json poll-info \
  --contract-address "$VOTE_CONTRACT_ADDRESS"
python scripts/somnia_vote_cli.py --config config.local.json results \
  --contract-address "$VOTE_CONTRACT_ADDRESS"
```

8. Optionally use `debug-void-vote` or `debug-cancel-pending` to reset a demo
   run. Use debug commands only in demo/dev mode.
9. Re-check the public wrapper before demos if needed:

```bash
WRAPPER_URL="https://somnia-ownership-wrapper-735868209397.europe-west1.run.app"
python scripts/check_public_wrapper.py --base-url "$WRAPPER_URL/owns" --collection-id <COLLECTION_ID> --wallet <DEMO_WALLET_ADDRESS> --token-id <TOKEN_ID> --expected-owns true
```

10. After the demo, recover leftover STT if needed:

```bash
python scripts/somnia_vote_cli.py --config config.local.json debug-withdraw-all-stt \
  --contract-address "$VOTE_CONTRACT_ADDRESS" \
  --to <RECIPIENT_ADDRESS>
```

11. After preserving evidence, decide whether to shut down or delete Cloud Run
   to limit cost exposure.

## Frontend Status

The first website demo is implemented in `frontend/` and is publicly deployed
at:

```text
https://somnia-agent.web.app
```

It connects MetaMask/injected EVM wallets, requires Somnia Shannon testnet,
accepts a `collectionId` and `tokenId`, displays `ChatGPT`, `Claude`, and
`DeepSeek`, submits `vote(collectionId, tokenId, choice)`, parses
`VoteRequested` request IDs from logs when available, polls collection-specific
token/pending state, and shows weighted result counts with leader/tie handling.
It also displays the configured accepted-vote reward and warns when
the vote contract balance is too low. The wrapper ownership precheck is
optional and informational; the on-chain callback remains authoritative.

Run locally:

```bash
cd frontend
npm install
npm run dev
```

Firebase Hosting deployment notes are in
[docs/frontend_deploy.md](frontend_deploy.md).
