# Cloud Run Deployment Report

Date: 2026-05-26

## Deployment

- Google Cloud project: `<GCP_PROJECT_ID>`
- Cloud Run region: `europe-west1`
- Cloud Run service: `somnia-ownership-wrapper`
- Public service URL: `https://somnia-ownership-wrapper-735868209397.europe-west1.run.app`

## Purpose

The wrapper is a public read-only HTTP service used by the Somnia JSON API
agent. It checks whether a wallet owns a specific Quills Adventure NFT token on
Somnia mainnet by calling `ownerOf(tokenId)`, and returns JSON containing both a
boolean `owns` field and an integer `ownsInt` field.

## Target Configuration

```text
TARGET_RPC_URL=https://api.infra.mainnet.somnia.network/
TARGET_NFT_CONTRACT=0x90780d0641a6328719a636ab289175e2155328a3
TARGET_CHAIN_LABEL=somnia-mainnet
TARGET_COLLECTION_LABEL=quills-adventure
```

## Endpoints

- `GET /health`
- `GET /owns?wallet=<address>&tokenId=<uint>`

## Verified Positive Case

```text
wallet=<DEMO_WALLET_ADDRESS>
tokenId=<TOKEN_ID>
```

Result:

```text
ok=true
owns=true
ownsInt=1
owner=<DEMO_WALLET_ADDRESS>
targetChain=somnia-mainnet
targetCollection=quills-adventure
```

## Verified Negative Case

```text
wallet=0x0000000000000000000000000000000000000000
tokenId=<TOKEN_ID>
```

Result:

```text
ok=true
owns=false
ownsInt=0
```

## Verification Commands

```bash
WRAPPER_URL="https://somnia-ownership-wrapper-735868209397.europe-west1.run.app"
curl -iS "$WRAPPER_URL/health"
curl -iS "$WRAPPER_URL/owns?wallet=<DEMO_WALLET_ADDRESS>&tokenId=<TOKEN_ID>"
```

Repo script check:

```bash
python scripts/check_public_wrapper.py \
  --base-url "$WRAPPER_URL/owns" \
  --wallet <DEMO_WALLET_ADDRESS> \
  --token-id <TOKEN_ID> \
  --expected-owns true
```

## Deployment Command Used

```bash
cd wrapper
gcloud run deploy somnia-ownership-wrapper \
  --source . \
  --region europe-west1 \
  --no-invoker-iam-check \
  --set-env-vars 'TARGET_RPC_URL=https://api.infra.mainnet.somnia.network/,TARGET_NFT_CONTRACT=0x90780d0641a6328719a636ab289175e2155328a3,TARGET_CHAIN_LABEL=somnia-mainnet,TARGET_COLLECTION_LABEL=quills-adventure'
```

## Operational Notes

- The wrapper is public and unauthenticated by design.
- It contains no private keys.
- It only performs read-only RPC calls to Somnia mainnet.
- Cloud Run supplies `PORT` automatically.
- A small Google Cloud budget alert was configured.
- The budget alert is not a hard spending cap.
- To inspect logs, use:

```bash
gcloud run services logs read somnia-ownership-wrapper --region europe-west1
```

- To temporarily disable/delete the service after the demo, use:

```bash
gcloud run services delete somnia-ownership-wrapper --region europe-west1
```

Do not run the delete command during the live demo setup.
