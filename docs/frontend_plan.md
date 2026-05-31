# Frontend Plan

The CLI path is proven, including the live Somnia JSON API agent callback. The
public website is:

```text
https://somnia-agent.web.app
```

The website should be configured around the next weighted AI poll contract:

```text
0x919eD02eba4772a72d6C75430026709009858754
```

The frontend:

- Uses MetaMask or another injected EVM wallet for signing.
- Targets Somnia Shannon testnet, chain ID `50312`.
- Calls the deployed AI poll contract, not the historical vote contract.
- Presents the poll: "Which AI assistant should lead the next agentic workflow?"
- Shows choices `ChatGPT`, `Claude`, and `DeepSeek`.
- Reads poll metadata from `pollQuestion()`, `choiceLabel(uint8)`, and
  `maxChoice()` when available.
- Falls back to public `VITE_*` labels when contract metadata cannot be read.
- Lets the user choose Quills Adventure or Bored Ape Yacht Club.
- Shows Quills Adventure on Somnia mainnet as voting power `1`.
- Shows Bored Ape Yacht Club on Ethereum mainnet as voting power `2`.
- Offers an optional wrapper pre-check for
  `GET /owns?collectionId=<COLLECTION_ID>&wallet=<DEMO_WALLET_ADDRESS>&tokenId=<TOKEN_ID>`.
- Treats the wrapper pre-check as informational only.
- Leaves the on-chain Somnia agent callback as the authoritative ownership
  decision.
- Displays weighted result counts, no-votes state, leader state, and tie state.
- Displays token state for the selected collection and entered token ID.
- Shows the successful-vote reward, vote contract balance, quoted request
  value, and low-balance warnings.
- Keeps demo/debug admin controls hidden unless
  `VITE_ENABLE_DEMO_ADMIN_TOOLS=true`.

The next public demo contract should be deployed with `reward_stt=1.02` and
selector path `votingPower`. After deployment, update frontend config to the new
`VITE_VOTE_CONTRACT_ADDRESS`, rebuild, and redeploy Firebase Hosting.

Future production/trustless deployments should remove all debug/admin contract
functions marked `TODO(DEMO-REMOVE)` and redeploy without centralized demo
reset or withdrawal powers.
