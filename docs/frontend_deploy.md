# Frontend Deploy

This deploys the static Vite frontend to Firebase Hosting. The current public
Hosting site is `somnia-agent`.

The public website is:

```text
https://somnia-agent.web.app
```

## Public Config

Frontend config is public and belongs in `frontend/.env` or in the deployment
environment. Do not put private keys, seed phrases, live wallet secrets, or
`config.local.json` values in frontend env files.

Start from:

```bash
cp frontend/.env.example frontend/.env
```

Current defaults:

```text
VITE_SOMNIA_CHAIN_ID=50312
VITE_SOMNIA_RPC_URL=https://api.infra.testnet.somnia.network/
VITE_SOMNIA_EXPLORER_URL=https://shannon-explorer.somnia.network
VITE_VOTE_CONTRACT_ADDRESS=0x919eD02eba4772a72d6C75430026709009858754
VITE_WRAPPER_BASE_URL=https://somnia-ownership-wrapper-735868209397.europe-west1.run.app
VITE_DEMO_VIDEO_URL=https://youtu.be/5rDhxTbaQ10
VITE_POLL_QUESTION="Which AI assistant should lead the next agentic workflow?"
VITE_CHOICE_1_LABEL=ChatGPT
VITE_CHOICE_2_LABEL=Claude
VITE_CHOICE_3_LABEL=DeepSeek
VITE_SUCCESS_REWARD_STT=1.02
VITE_COLLECTION_1_LABEL=Quills Adventure
VITE_COLLECTION_1_CHAIN=Somnia mainnet
VITE_COLLECTION_1_POWER=1
VITE_COLLECTION_2_LABEL=Bored Ape Yacht Club
VITE_COLLECTION_2_CHAIN=Ethereum mainnet
VITE_COLLECTION_2_POWER=2
VITE_ENABLE_DEMO_ADMIN_TOOLS=false
```

After deploying the next weighted contract, update
`VITE_VOTE_CONTRACT_ADDRESS` to the new `VOTE_CONTRACT_ADDRESS`, rebuild, and
redeploy Hosting.

To update the demo video later, set:

```bash
VITE_DEMO_VIDEO_URL="https://www.youtube.com/watch?v=REPLACE_WITH_VIDEO_ID"
```

## Local Run

Install Node.js with npm if it is missing, then run:

```bash
cd frontend
npm install
npm run dev
```

Open the printed local URL. The frontend uses MetaMask or another injected EVM
wallet. It never asks for a private key.

## Build And Preview

```bash
cd frontend
npm run typecheck
npm run build
npm run preview
```

The static build output is `frontend/dist`.

## Firebase Hosting Deploy

Install the Firebase CLI if it is not already available:

```bash
npm install -g firebase-tools
```

Authenticate and select the project:

```bash
firebase login
firebase use <FIREBASE_PROJECT_ID>
```

Build and deploy only Hosting:

```bash
cd frontend
npm install
npm run build
cd ..
firebase deploy --only hosting
```

The root `firebase.json` serves `frontend/dist`, targets the `somnia-agent`
Hosting site, and rewrites all routes to `/index.html` for the single-page app.

## New Contract Deployment Reminder

Deploy the updated Cloud Run wrapper with both collection RPC configs. For the
next public demo, deploy a fresh weighted AI poll contract with
`--reward-stt 1.02`, selector path `votingPower`, fund it, then update frontend
config to the new contract address before rebuilding and deploying.

Because successful votes now pay about `1.02 STT` plus the JSON API request
value from the vote contract balance, top up the vote contract before public
demos. A practical starting balance is at least `10 STT`.

## Cloud Run Fallback

Use Firebase Hosting first. If Hosting is blocked, build the frontend and serve
`frontend/dist` from any minimal static server container on Cloud Run. Keep the
same public `VITE_*` values at build time and do not add private keys or local
deployment config to the image.
