# Live Somnia JSON API Notes

This file records the live-agent assumptions currently used by the repo. Do not
put private keys, deployed local config, or billing data here.

## Documented Values

Source: Somnia's May 2026 agent developer guide and current Somnia network docs.

```text
Somnia Shannon chain_id=50312
Somnia Shannon explorer=https://shannon-explorer.somnia.network/
Somnia Shannon platform=0x037Bb9C718F3f7fe5eCBDB0b600D607b52706776
JSON API agent_id=13174292974160097713
documented method=fetchUint(string,string,uint8)
documented method selector=0x3bbc1302
price_per_validator=0.03 STT
default_subcommittee_size=3
request_value=getRequestDeposit() + price_per_validator * subcommittee_size
expected JSON API selector path=votingPower
expected decimals=0
```

The prior bool-oriented path is intentionally not used for live deployments.
The retrievable public guide documents `fetchUint(...)` and typed ABI decoding,
but not a concrete `fetchBool(...)` example.

## Repo Mapping

The wrapper returns ownership fields plus weighted voting power:

```json
{
  "collectionId": 1,
  "owns": true,
  "ownsInt": 1,
  "votingPower": 1
}
```

The human-readable `owns` field remains useful for curl/debug output. The live
Somnia agent should select `votingPower` and decode a `uint256`; the voting
contract records positive values as weighted votes and rejects zero.

## Probe-First Sequence

Before deploying the real voting contract against the official platform:

1. Deploy the wrapper to Cloud Run.
2. Curl the public wrapper with a collection, demo wallet, and token pair:
   `collectionId=<COLLECTION_ID>`, `wallet=<DEMO_WALLET_ADDRESS>`,
   `tokenId=<TOKEN_ID>`.
3. Run `scripts/check_public_wrapper.py` against the public wrapper URL.
4. Deploy `JsonApiUintProbe`.
5. Submit one `probe-request` against the public wrapper URL.
6. Confirm `probe-read` reports `lastDecodeOk=True` and the expected
   `lastDecodedUint` voting power.
7. Only then deploy `NftGatedVote` against the official platform.

## Demo Wallet Constraint

The successful Quills-gated vote must be submitted from the same EVM address
that owns the Quills NFT on Somnia mainnet. Use placeholders in generic docs and
examples:

```text
wallet=<DEMO_WALLET_ADDRESS>
tokenId=<TOKEN_ID>
```
