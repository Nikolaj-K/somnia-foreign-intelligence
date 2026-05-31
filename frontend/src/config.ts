const env = import.meta.env;

const FALLBACK_CHAIN_ID = 50312;
const FALLBACK_EXPLORER_URL = "https://shannon-explorer.somnia.network";
const FALLBACK_RPC_URL = "https://api.infra.testnet.somnia.network/";
const FALLBACK_WRAPPER_BASE_URL =
  "https://somnia-ownership-wrapper-735868209397.europe-west1.run.app";
const FALLBACK_VOTE_CONTRACT =
  "0x0000000000000000000000000000000000000000";
const FALLBACK_DEMO_VIDEO_URL =
  "https://youtu.be/5rDhxTbaQ10";
const FALLBACK_SUCCESS_REWARD_STT = "1.02";

function cleanUrl(value: string): string {
  return value.replace(/\/+$/, "");
}

function readNumber(value: string | undefined, fallback: number): number {
  if (!value) {
    return fallback;
  }
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : fallback;
}

export const FALLBACK_CHOICES = [
  { id: 1, label: env.VITE_CHOICE_1_LABEL || "ChatGPT" },
  { id: 2, label: env.VITE_CHOICE_2_LABEL || "Claude" },
  { id: 3, label: env.VITE_CHOICE_3_LABEL || "DeepSeek" }
] as const;

export const FALLBACK_COLLECTIONS = [
  {
    id: 1,
    label: env.VITE_COLLECTION_1_LABEL || "Quills Adventure",
    contractLabel: "quills-adventure",
    chain: env.VITE_COLLECTION_1_CHAIN || "Somnia mainnet",
    power: readNumber(env.VITE_COLLECTION_1_POWER, 1)
  },
  {
    id: 2,
    label: env.VITE_COLLECTION_2_LABEL || "Bored Ape Yacht Club",
    contractLabel: "bored-ape-yacht-club",
    chain: env.VITE_COLLECTION_2_CHAIN || "Ethereum mainnet",
    power: readNumber(env.VITE_COLLECTION_2_POWER, 2)
  }
] as const;

export const APP_CONFIG = {
  somniaChainId: readNumber(env.VITE_SOMNIA_CHAIN_ID, FALLBACK_CHAIN_ID),
  somniaRpcUrl: env.VITE_SOMNIA_RPC_URL || FALLBACK_RPC_URL,
  somniaExplorerUrl: cleanUrl(
    env.VITE_SOMNIA_EXPLORER_URL || FALLBACK_EXPLORER_URL
  ),
  voteContractAddress:
    env.VITE_VOTE_CONTRACT_ADDRESS || FALLBACK_VOTE_CONTRACT,
  wrapperBaseUrl: cleanUrl(
    env.VITE_WRAPPER_BASE_URL || FALLBACK_WRAPPER_BASE_URL
  ),
  demoVideoUrl: env.VITE_DEMO_VIDEO_URL || FALLBACK_DEMO_VIDEO_URL,
  pollQuestion:
    env.VITE_POLL_QUESTION ||
    "Which AI assistant should lead the next agentic workflow?",
  successRewardStt: env.VITE_SUCCESS_REWARD_STT || FALLBACK_SUCCESS_REWARD_STT,
  enableDemoAdminTools: env.VITE_ENABLE_DEMO_ADMIN_TOOLS === "true"
} as const;

export function somniaChainIdHex(): `0x${string}` {
  return `0x${APP_CONFIG.somniaChainId.toString(16)}`;
}
