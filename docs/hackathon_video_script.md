# Hackathon Video Script Draft

Working title:

```text
NFT-gated voting on Somnia, powered by an agent-read ownership check
```

## Short Script

I am building a Somnia testnet voting demo where voting rights come from NFT
ownership in another chain context.

The target collections are Quills Adventure on Somnia mainnet and Bored Ape
Yacht Club on Ethereum mainnet. The voting contract itself lives on Somnia
Shannon testnet. A user chooses a collection, submits a token ID and a vote
choice. The contract then asks a Somnia JSON API agent to call a public wrapper
endpoint. That wrapper checks the selected ERC-721 contract with
`ownerOf(tokenId)` and returns simple JSON fields:

```json
{"collectionId": 2, "owns": true, "ownsInt": 1, "votingPower": 2}
```

The live Somnia agent path selects `votingPower` with the documented
`fetchUint(string,string,uint8)` method.

If the agent callback says the caller owns that token, the Somnia contract
records a weighted vote and optionally pays a small testnet STT incentive.

The important part is not the incentive. The important part is that the voting
contract can use agent-mediated external data to make an on-chain decision.

For the hackathon MVP, this is deliberately not a trustless bridge. The trust
path is:

```text
Somnia contract -> Somnia agent platform -> public wrapper -> target RPC -> NFT contract
```

That is enough for a practical demo, and it gives a clean path for future
versions: direct JSON-RPC agent support, multiple independent wrappers, storage
proofs, shadow credentials, or a full cross-chain proof layer.

## Demo Beats

1. Show the collection selector for Quills and BAYC.
2. Show the wrapper endpoint returning `owns: true` and `votingPower`.
3. Show the probe contract proving the live JSON API callback/decode path.
4. Show the Somnia testnet contract receiving a vote request.
5. Show the async callback accepting or rejecting the vote.
6. Show the recorded vote count and token vote state.

## Current Caveat

A successful live vote requires the Somnia testnet voting wallet to have the
same EVM address as the selected NFT owner on that NFT's source chain.
