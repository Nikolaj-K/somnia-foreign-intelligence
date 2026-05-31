# Ownership Wrapper

HTTP wrapper for the Somnia JSON API Request agent.

Endpoint:

```text
GET /owns?collectionId=<uint>&wallet=<address>&tokenId=<uint>
```

If `collectionId` is omitted, the wrapper defaults to Quills Adventure
`collectionId=1`.

It calls `ownerOf(tokenId)` on the configured ERC-721 collection and returns
JSON with `owns`, `ownsInt`, and `votingPower`. The Somnia live JSON API
selector should be:

```text
votingPower
```

Use `votingPower` with the documented `fetchUint(string,string,uint8)` method
and `decimals = 0`.

## Collections

| ID | Collection | Chain | Voting power |
| --- | --- | --- | ---: |
| 1 | Quills Adventure | Somnia mainnet | 1 |
| 2 | Bored Ape Yacht Club | Ethereum mainnet | 2 |

## Environment

```bash
QUILLS_RPC_URL=https://api.infra.mainnet.somnia.network/
QUILLS_NFT_CONTRACT=0x90780d0641a6328719a636ab289175e2155328a3
BAYC_RPC_URL=<ethereum-mainnet-rpc-url>
BAYC_NFT_CONTRACT=0xbc4ca0eda7647a8ab7c2061c2e118a18a936f13d
PORT=8080
```

The committed BAYC fallback uses a public Ethereum RPC URL that may be
rate-limited. For Cloud Run demos, set `BAYC_RPC_URL` server-side. Do not put
RPC API keys or other secrets in tracked files.

## Local Run

From the repo root:

```bash
source .venv/bin/activate
export QUILLS_RPC_URL='https://api.infra.mainnet.somnia.network/'
export QUILLS_NFT_CONTRACT='0x90780d0641a6328719a636ab289175e2155328a3'
export BAYC_RPC_URL='<ethereum-mainnet-rpc-url>'
export BAYC_NFT_CONTRACT='0xbc4ca0eda7647a8ab7c2061c2e118a18a936f13d'
flask --app wrapper.app run --host 127.0.0.1 --port 8080
```

In another terminal:

```bash
curl -sS 'http://127.0.0.1:8080/health'
curl -sS 'http://127.0.0.1:8080/owns?collectionId=1&wallet=<DEMO_WALLET>&tokenId=<TOKEN_ID>'
curl -sS 'http://127.0.0.1:8080/owns?collectionId=2&wallet=<DEMO_WALLET>&tokenId=<TOKEN_ID>'
```

All error paths return JSON with `"votingPower": 0` so the agent can safely
extract a zero value when the wrapper responds with HTTP 200. Invalid
`collectionId` returns a clear JSON error with HTTP 400.

See `wrapper/DEPLOY.md` for the current Cloud Run deployment runbook.
