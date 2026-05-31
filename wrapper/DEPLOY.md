# Deploying The Ownership Wrapper To Cloud Run

This is the public endpoint the Somnia JSON API Request agent calls.

The service is stateless. It exposes:

```text
GET /health
GET /owns?collectionId=<uint>&wallet=<address>&tokenId=<uint>
```

If `collectionId` is omitted, the wrapper defaults to Quills Adventure
`collectionId=1` for compatibility with the first demo. New contract and
frontend paths pass `collectionId` explicitly.

## Environment

Cloud Run supplies `PORT` automatically. Do not set or store private keys,
wallet secrets, seed phrases, or signing credentials in this service.

Required or strongly recommended environment variables:

```text
QUILLS_RPC_URL=https://api.infra.mainnet.somnia.network/
QUILLS_NFT_CONTRACT=0x90780d0641a6328719a636ab289175e2155328a3
BAYC_RPC_URL=<ETHEREUM_MAINNET_RPC_URL>
BAYC_NFT_CONTRACT=0xbc4ca0eda7647a8ab7c2061c2e118a18a936f13d
```

The committed default for BAYC uses a public Ethereum RPC fallback, which may
be rate-limited. For Cloud Run demos, set `BAYC_RPC_URL` to a reliable
server-side Ethereum mainnet RPC URL. If that URL contains an API key, store it
only in Cloud Run environment configuration or local ignored config, never in
git.

The wrapper only performs read-only `eth_call` requests.

## Local Container Check

From the repo root:

```bash
cd wrapper
docker build -t somnia-ownership-wrapper .
docker run --rm -p 8080:8080 \
  -e QUILLS_RPC_URL='https://api.infra.mainnet.somnia.network/' \
  -e QUILLS_NFT_CONTRACT='0x90780d0641a6328719a636ab289175e2155328a3' \
  -e BAYC_RPC_URL='<ETHEREUM_MAINNET_RPC_URL>' \
  -e BAYC_NFT_CONTRACT='0xbc4ca0eda7647a8ab7c2061c2e118a18a936f13d' \
  somnia-ownership-wrapper
```

In another terminal:

```bash
curl -sS 'http://127.0.0.1:8080/health'
curl -sS 'http://127.0.0.1:8080/owns?collectionId=1&wallet=<DEMO_WALLET_ADDRESS>&tokenId=<TOKEN_ID>'
curl -sS 'http://127.0.0.1:8080/owns?collectionId=2&wallet=<DEMO_WALLET_ADDRESS>&tokenId=<TOKEN_ID>'
```

## Cloud Run: Project Setup

These commands assume the Google Cloud SDK is installed on your Mac.

```bash
gcloud auth login
gcloud projects list
gcloud config set project YOUR_GCP_PROJECT_ID
gcloud config set run/region europe-west1
gcloud services enable run.googleapis.com cloudbuild.googleapis.com artifactregistry.googleapis.com
```

Link billing before deploying, and set a small budget alert in Google Cloud
Billing.

## Cloud Run: Deploy

Deploy from the `wrapper/` directory:

```bash
cd /path/to/foreign_intelligence/wrapper
gcloud run deploy somnia-ownership-wrapper \
  --source . \
  --region europe-west1 \
  --allow-unauthenticated \
  --set-env-vars QUILLS_RPC_URL=https://api.infra.mainnet.somnia.network/,QUILLS_NFT_CONTRACT=0x90780d0641a6328719a636ab289175e2155328a3,BAYC_RPC_URL=<ETHEREUM_MAINNET_RPC_URL>,BAYC_NFT_CONTRACT=0xbc4ca0eda7647a8ab7c2061c2e118a18a936f13d
```

The command prints the service URL. Verify it:

```bash
WRAPPER_URL='https://YOUR_CLOUD_RUN_URL'
curl -sS "$WRAPPER_URL/health"
curl -sS "$WRAPPER_URL/owns?collectionId=1&wallet=<DEMO_WALLET_ADDRESS>&tokenId=<TOKEN_ID>"
curl -sS "$WRAPPER_URL/owns?collectionId=2&wallet=<DEMO_WALLET_ADDRESS>&tokenId=<TOKEN_ID>"
```

From the repo root, with `.venv` active, run the stricter JSON shape check:

```bash
source .venv/bin/activate
python scripts/check_public_wrapper.py --base-url "$WRAPPER_URL/owns" --collection-id 1 --wallet <DEMO_WALLET_ADDRESS> --token-id <TOKEN_ID> --expected-owns true
python scripts/check_public_wrapper.py --base-url "$WRAPPER_URL/owns" --collection-id 2 --wallet <DEMO_WALLET_ADDRESS> --token-id <TOKEN_ID>
```

Expected shape:

```json
{
  "ok": true,
  "collectionId": 2,
  "collection": "bayc",
  "wallet": "0x...",
  "tokenId": "1234",
  "owner": "0x...",
  "owns": true,
  "ownsInt": 1,
  "votingPower": 2,
  "targetChain": "ethereum-mainnet",
  "targetCollection": "bored-ape-yacht-club",
  "targetNftContract": "0xbc4ca0eda7647a8ab7c2061c2e118a18a936f13d",
  "checkedBlock": 123
}
```

`checkedBlock` will be the live source-chain block number.

## Notes

- This service is public and unauthenticated by design because the Somnia agent
  must be able to fetch it.
- The live contract path should select `votingPower` with Somnia's documented
  `fetchUint(string,string,uint8)` method and `decimals = 0`.
- Budget alerts should be configured in Google Cloud before a public demo.
