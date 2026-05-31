/// <reference types="vite/client" />

interface ImportMetaEnv {
  readonly VITE_SOMNIA_CHAIN_ID?: string;
  readonly VITE_SOMNIA_RPC_URL?: string;
  readonly VITE_SOMNIA_EXPLORER_URL?: string;
  readonly VITE_VOTE_CONTRACT_ADDRESS?: string;
  readonly VITE_WRAPPER_BASE_URL?: string;
  readonly VITE_DEMO_VIDEO_URL?: string;
  readonly VITE_POLL_QUESTION?: string;
  readonly VITE_CHOICE_1_LABEL?: string;
  readonly VITE_CHOICE_2_LABEL?: string;
  readonly VITE_CHOICE_3_LABEL?: string;
  readonly VITE_SUCCESS_REWARD_STT?: string;
  readonly VITE_COLLECTION_1_LABEL?: string;
  readonly VITE_COLLECTION_1_CHAIN?: string;
  readonly VITE_COLLECTION_1_POWER?: string;
  readonly VITE_COLLECTION_2_LABEL?: string;
  readonly VITE_COLLECTION_2_CHAIN?: string;
  readonly VITE_COLLECTION_2_POWER?: string;
  readonly VITE_ENABLE_DEMO_ADMIN_TOOLS?: string;
}

interface ImportMeta {
  readonly env: ImportMetaEnv;
}

type Eip1193Listener = (...args: unknown[]) => void;

interface Eip1193Provider {
  request(args: { method: string; params?: unknown[] }): Promise<unknown>;
  on?(eventName: string, listener: Eip1193Listener): void;
  removeListener?(eventName: string, listener: Eip1193Listener): void;
}

interface Window {
  ethereum?: Eip1193Provider;
}
