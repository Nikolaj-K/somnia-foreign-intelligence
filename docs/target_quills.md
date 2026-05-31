# Quills Adventure Target Notes

Quills Adventure is collection `1` in the weighted voting demo.

```text
Chain: Somnia mainnet
RPC: https://api.infra.mainnet.somnia.network/
Contract: 0x90780d0641a6328719a636ab289175e2155328a3
Voting power: 1
```

The collection appears to use token IDs `1..3333`; token ID `0` reverts.
Demo wallet/token pairs should be kept out of generic docs. Use placeholders:

```text
owner=<DEMO_WALLET_ADDRESS>
token_id=<TOKEN_ID>
```

Wrapper environment example:

```bash
export QUILLS_RPC_URL='https://api.infra.mainnet.somnia.network/'
export QUILLS_NFT_CONTRACT='0x90780d0641a6328719a636ab289175e2155328a3'
```

The voting contract accepts a vote only when the wrapper reports positive
`votingPower` through the Somnia JSON API callback. For Quills, that value is
`1`.
