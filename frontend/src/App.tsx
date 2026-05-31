import {
  AlertTriangle,
  Bot,
  CheckCircle2,
  Copy,
  ArrowDown,
  ExternalLink,
  Loader2,
  Network,
  PlayCircle,
  RefreshCw,
  Settings,
  ShieldCheck,
  Trophy,
  Vote,
  Wallet,
  XCircle
} from "lucide-react";
import { useCallback, useEffect, useMemo, useState } from "react";
import type { ReactElement, ReactNode } from "react";
import {
  BrowserProvider,
  Contract,
  JsonRpcProvider,
  formatEther,
  isAddress,
  parseEther
} from "ethers";

import {
  APP_CONFIG,
  FALLBACK_CHOICES,
  FALLBACK_COLLECTIONS,
  somniaChainIdHex
} from "./config";
import { NFT_GATED_VOTE_ABI } from "./contractAbi";
import {
  ChoiceCount,
  buildExplorerAddressUrl,
  buildExplorerTxUrl,
  buildWrapperOwnsUrl,
  calculateLeader,
  isUintInput,
  parseYoutubeEmbedUrl,
  shortenHex
} from "./utils";

type WalletState = {
  address: string;
  chainId: number | null;
};

type PollMetadata = {
  question: string;
  maxChoice: number;
  choices: ChoiceCount[];
  source: "contract" | "env fallback";
};

type CollectionMetadata = {
  id: number;
  label: string;
  contractLabel: string;
  chain: string;
  power: number;
  source: "contract" | "env fallback";
};

type ContractLeader = {
  choice: number;
  votes: bigint;
  hasVotes: boolean;
  isTie: boolean;
};

type ResultsState = {
  choices: ChoiceCount[];
  leader: ReturnType<typeof calculateLeader>;
  contractLeader: ContractLeader | null;
  contractBalanceWei: bigint;
  requestValueWei: bigint | null;
  rewardWei: bigint;
  rewardSource: "contract" | "env fallback";
  lowBalanceThresholdWei: bigint;
  loadedAt: Date;
};

type RankedChoice = {
  choice: ChoiceCount;
  rank: number;
  label: string;
  tone: "first" | "second" | "third" | "tied" | "empty";
  isTied: boolean;
};

type PendingVoteState = {
  requestId: bigint;
  exists: boolean;
  voter: string;
  collectionId: number;
  tokenId: bigint;
  choice: number;
  createdAt: bigint;
};

type TokenVoteState = {
  collectionId: number;
  tokenId: string;
  hasVoted: boolean;
  choice: number;
  voter: string;
  votingPower: bigint;
  pendingRequestId: bigint;
  pending: PendingVoteState | null;
};

type WrapperPrecheckState =
  | { status: "idle" }
  | { status: "checking" }
  | { status: "ok"; url: string; data: Record<string, unknown> }
  | { status: "error"; url?: string; message: string };

type VoteFlowState = {
  status: "idle" | "submitting" | "pending" | "accepted" | "rejected" | "error";
  txHash?: string;
  requestId?: bigint;
  collectionId?: number;
  tokenId?: string;
  choice?: number;
  message?: string;
};

type FlowStatusCopy = {
  summary: string;
  detail?: string;
};

const MIN_DEMO_BALANCE_WARNING_WEI = parseEther("2");
const COLLECTION_ICON_BY_ID: Record<number, string> = {
  1: "/599858fa36e3c7b1feb8821db0d8af83.avif",
  2: "/873c134b69c0d3024ea39690e5bacc36.avif"
};
const WRAPPER_SAMPLE_URL =
  "https://somnia-ownership-wrapper-735868209397.europe-west1.run.app/owns?collectionId=2&wallet=0x0000000000000000000000000000000000000000&tokenId=809";

function fallbackMetadata(): PollMetadata {
  return {
    question: APP_CONFIG.pollQuestion,
    maxChoice: FALLBACK_CHOICES.length,
    choices: FALLBACK_CHOICES.map((choice) => ({
      choice: choice.id,
      label: choice.label,
      count: 0n
    })),
    source: "env fallback"
  };
}

function fallbackCollections(): CollectionMetadata[] {
  return FALLBACK_COLLECTIONS.map((collection) => ({
    ...collection,
    source: "env fallback" as const
  }));
}

function errorMessage(error: unknown): string {
  if (error instanceof Error) {
    return error.message;
  }
  if (typeof error === "object" && error && "message" in error) {
    return String((error as { message: unknown }).message);
  }
  return String(error);
}

function defaultVoteFlowMessage(status: VoteFlowState["status"]): string {
  if (status === "idle") {
    return "Ready to submit.";
  }
  return "";
}

function revertReasonFromMessage(message: string): string {
  const reasonMatch =
    message.match(/reason="([^"]+)"/) ||
    message.match(/execution reverted: "([^"]+)"/) ||
    message.match(/reverted with reason string '([^']+)'/);
  return reasonMatch?.[1] || "";
}

function flowStatusCopy(status: VoteFlowState["status"], message?: string): FlowStatusCopy {
  const rawMessage = (message || defaultVoteFlowMessage(status)).trim();
  if (!rawMessage) {
    return { summary: "" };
  }
  if (status !== "error" && rawMessage.length <= 220) {
    return { summary: rawMessage };
  }

  const reason = status === "error" ? revertReasonFromMessage(rawMessage) : "";
  if (reason) {
    return {
      summary: `Reverted: ${reason}.`,
      detail: rawMessage
    };
  }
  if (rawMessage.length > 220) {
    return {
      summary: `${rawMessage.slice(0, 220).trim()}...`,
      detail: rawMessage
    };
  }
  return { summary: rawMessage };
}

function normalizeChoice(value: unknown): number {
  return Number(value);
}

function choiceLabelFor(choices: ChoiceCount[], choice: number): string {
  return choices.find((item) => item.choice === choice)?.label || `Choice ${choice}`;
}

function collectionValidationLabel(collection: CollectionMetadata): string {
  if (collection.id === 1) {
    return "Validate on Somnia Mainnet";
  }
  if (collection.id === 2) {
    return "Validate on Ethereum Mainnet";
  }
  return `Validate on ${collection.chain}`;
}

function sttAmount(valueWei: bigint | null | undefined, digits = 4): string {
  if (valueWei === null || valueWei === undefined) {
    return "Unavailable";
  }
  const raw = Number(formatEther(valueWei));
  if (!Number.isFinite(raw)) {
    return `${formatEther(valueWei)} STT`;
  }
  return `${raw.toFixed(digits)} STT`;
}

function rankChoices(choices: ChoiceCount[]): RankedChoice[] {
  const sorted = [...choices].sort((left, right) => {
    if (left.count === right.count) {
      return left.choice - right.choice;
    }
    return right.count > left.count ? 1 : -1;
  });
  const allEmpty = sorted.every((choice) => choice.count === 0n);

  return sorted.map((choice, index) => {
    const firstSameCountIndex = sorted.findIndex((item) => item.count === choice.count);
    const tiedCount = sorted.filter((item) => item.count === choice.count).length;
    const rank = firstSameCountIndex + 1;
    const isTied = !allEmpty && tiedCount > 1;
    const tone =
      allEmpty ? "empty" : isTied ? "tied" : rank === 1 ? "first" : rank === 2 ? "second" : "third";
    const label = allEmpty ? "Open" : isTied ? `Tied #${rank}` : `#${index + 1}`;

    return {
      choice,
      rank,
      label,
      tone,
      isTied
    };
  });
}

export default function App() {
  const readProvider = useMemo(
    () => new JsonRpcProvider(APP_CONFIG.somniaRpcUrl, APP_CONFIG.somniaChainId),
    []
  );
  const readContract = useMemo(
    () =>
      new Contract(
        APP_CONFIG.voteContractAddress,
        NFT_GATED_VOTE_ABI,
        readProvider
      ),
    [readProvider]
  );

  const [wallet, setWallet] = useState<WalletState | null>(null);
  const [metadata, setMetadata] = useState<PollMetadata>(fallbackMetadata);
  const [collections, setCollections] = useState<CollectionMetadata[]>(fallbackCollections);
  const [selectedCollectionId, setSelectedCollectionId] = useState(1);
  const [results, setResults] = useState<ResultsState | null>(null);
  const [tokenId, setTokenId] = useState("");
  const [selectedChoice, setSelectedChoice] = useState(1);
  const [tokenState, setTokenState] = useState<TokenVoteState | null>(null);
  const [precheck, setPrecheck] = useState<WrapperPrecheckState>({ status: "idle" });
  const [voteFlow, setVoteFlow] = useState<VoteFlowState>({ status: "idle" });
  const [statusMessage, setStatusMessage] = useState("");
  const [isRefreshing, setIsRefreshing] = useState(false);
  const [copiedValue, setCopiedValue] = useState("");
  const [adminAddress, setAdminAddress] = useState("");
  const [adminRequestId, setAdminRequestId] = useState("");
  const [adminWithdrawTo, setAdminWithdrawTo] = useState("");
  const [adminWithdrawAmount, setAdminWithdrawAmount] = useState("");

  const connectedToSomnia = wallet?.chainId === APP_CONFIG.somniaChainId;
  const tokenInputValid = isUintInput(tokenId);
  const videoEmbedUrl = parseYoutubeEmbedUrl(APP_CONFIG.demoVideoUrl);
  const flowChoices = metadata.choices.length ? metadata.choices : fallbackMetadata().choices;
  const activeCollections = collections.length ? collections : fallbackCollections();
  const selectedCollection =
    activeCollections.find((collection) => collection.id === selectedCollectionId) ||
    activeCollections[0] ||
    fallbackCollections()[0];

  const copyValue = useCallback(async (value: string) => {
    await navigator.clipboard.writeText(value);
    setCopiedValue(value);
    window.setTimeout(() => setCopiedValue(""), 1400);
  }, []);

  const refreshWalletState = useCallback(async () => {
    if (!window.ethereum) {
      return;
    }
    const provider = new BrowserProvider(window.ethereum);
    const accounts = (await window.ethereum.request({
      method: "eth_accounts"
    })) as string[];
    const network = await provider.getNetwork();
    setWallet({
      address: accounts[0] || "",
      chainId: Number(network.chainId)
    });
  }, []);

  const connectWallet = useCallback(async () => {
    if (!window.ethereum) {
      setStatusMessage("No injected EVM wallet found. Install MetaMask or another injected wallet.");
      return;
    }
    await window.ethereum.request({ method: "eth_requestAccounts" });
    await refreshWalletState();
  }, [refreshWalletState]);

  const switchToSomnia = useCallback(async () => {
    if (!window.ethereum) {
      setStatusMessage("No injected EVM wallet found.");
      return;
    }

    try {
      await window.ethereum.request({
        method: "wallet_switchEthereumChain",
        params: [{ chainId: somniaChainIdHex() }]
      });
    } catch (error) {
      const code = Number((error as { code?: unknown }).code);
      if (code !== 4902) {
        setStatusMessage(errorMessage(error));
        return;
      }
      await window.ethereum.request({
        method: "wallet_addEthereumChain",
        params: [
          {
            chainId: somniaChainIdHex(),
            chainName: "Somnia Shannon Testnet",
            nativeCurrency: {
              name: "STT",
              symbol: "STT",
              decimals: 18
            },
            rpcUrls: [APP_CONFIG.somniaRpcUrl],
            blockExplorerUrls: [APP_CONFIG.somniaExplorerUrl]
          }
        ]
      });
    } finally {
      await refreshWalletState();
    }
  }, [refreshWalletState]);

  const refreshMetadata = useCallback(async () => {
    try {
      const maxChoice = normalizeChoice(await readContract.maxChoice());
      const question = String(await readContract.pollQuestion());
      const labels = await Promise.all(
        Array.from({ length: maxChoice }, async (_, index) =>
          String(await readContract.choiceLabel(index + 1))
        )
      );
      const nextMetadata: PollMetadata = {
        question,
        maxChoice,
        choices: labels.map((label, index) => ({
          choice: index + 1,
          label: label || `Choice ${index + 1}`,
          count: 0n
        })),
        source: "contract"
      };
      setMetadata(nextMetadata);
      return nextMetadata;
    } catch {
      const fallback = fallbackMetadata();
      setMetadata(fallback);
      return fallback;
    }
  }, [readContract]);

  const refreshCollections = useCallback(async () => {
    try {
      const ids = ((await readContract.supportedCollectionIds()) as bigint[]).map((id) =>
        Number(id)
      );
      const nextCollections = await Promise.all(
        ids.map(async (id) => {
          const [contractLabel, displayLabel, chainLabel, votingPower] =
            await Promise.all([
              readContract.collectionLabel(id).catch(() => ""),
              readContract.collectionDisplayLabel(id).catch(() => ""),
              readContract.collectionChainLabel(id).catch(() => ""),
              readContract.collectionVotingPower(id).catch(() => 0n)
            ]);
          const fallback = fallbackCollections().find((item) => item.id === id);
          return {
            id,
            label: String(displayLabel || fallback?.label || `Collection ${id}`),
            contractLabel: String(
              contractLabel || fallback?.contractLabel || `collection-${id}`
            ),
            chain: String(chainLabel || fallback?.chain || "Unknown chain"),
            power: Number(votingPower || fallback?.power || 0),
            source: "contract" as const
          };
        })
      );
      setCollections(nextCollections.length ? nextCollections : fallbackCollections());
      return nextCollections;
    } catch {
      const fallback = fallbackCollections();
      setCollections(fallback);
      return fallback;
    }
  }, [readContract]);

  const refreshResults = useCallback(
    async (pollMetadata: PollMetadata) => {
      const fallbackChoices = pollMetadata.choices;
      let counts: bigint[];
      let contractLeader: ContractLeader | null = null;

      try {
        counts = (await readContract.getAllChoiceCounts()) as bigint[];
      } catch {
        counts = await Promise.all(
          fallbackChoices.map(
            async (choice) => (await readContract.getChoiceCount(choice.choice)) as bigint
          )
        );
      }

      try {
        const rawLeader = (await readContract.leadingChoice()) as [
          bigint,
          bigint,
          boolean,
          boolean
        ];
        contractLeader = {
          choice: Number(rawLeader[0]),
          votes: rawLeader[1],
          hasVotes: rawLeader[2],
          isTie: rawLeader[3]
        };
      } catch {
        contractLeader = null;
      }

      const choices = fallbackChoices.map((choice, index) => ({
        ...choice,
        count: counts[index] || 0n
      }));
      const fallbackRewardWei = parseEther(APP_CONFIG.successRewardStt);
      const [contractBalanceWei, requestValueWei, rewardQuote] = await Promise.all([
        readProvider.getBalance(APP_CONFIG.voteContractAddress),
        readContract.quoteRequestValueWei().catch(() => null),
        readContract
          .rewardWei()
          .then((value: bigint) => ({
            value,
            source: "contract" as const
          }))
          .catch(() => ({
            value: fallbackRewardWei,
            source: "env fallback" as const
          }))
      ]);
      const typedRequestValueWei = requestValueWei as bigint | null;
      const minimumAcceptedVoteCostWei =
        (typedRequestValueWei || 0n) + rewardQuote.value;
      const lowBalanceThresholdWei =
        minimumAcceptedVoteCostWei > MIN_DEMO_BALANCE_WARNING_WEI
          ? minimumAcceptedVoteCostWei
          : MIN_DEMO_BALANCE_WARNING_WEI;

      const nextResults: ResultsState = {
        choices,
        leader: calculateLeader(choices),
        contractLeader,
        contractBalanceWei,
        requestValueWei: typedRequestValueWei,
        rewardWei: rewardQuote.value,
        rewardSource: rewardQuote.source,
        lowBalanceThresholdWei,
        loadedAt: new Date()
      };
      setResults(nextResults);
      return nextResults;
    },
    [readContract, readProvider]
  );

  const refreshTokenState = useCallback(
    async (knownRequestId?: bigint) => {
      if (!tokenInputValid) {
        setTokenState(null);
        return null;
      }

      const token = BigInt(tokenId);
      const [hasVoted, choice, voter, votingPower, tokenPendingRequest] = await Promise.all([
        readContract.hasTokenVoted(selectedCollectionId, token),
        readContract.getTokenVote(selectedCollectionId, token),
        readContract.tokenVoter(selectedCollectionId, token),
        readContract.tokenVotingPower(selectedCollectionId, token),
        readContract.tokenPendingRequest(selectedCollectionId, token)
      ]);

      const pendingRequestId =
        (tokenPendingRequest as bigint) !== 0n
          ? (tokenPendingRequest as bigint)
          : knownRequestId || 0n;
      let pending: PendingVoteState | null = null;
      if (pendingRequestId !== 0n) {
        const rawPending = (await readContract.pendingVotes(pendingRequestId)) as [
          boolean,
          string,
          bigint,
          bigint,
          bigint,
          bigint
        ];
        pending = {
          requestId: pendingRequestId,
          exists: rawPending[0],
          voter: rawPending[1],
          collectionId: Number(rawPending[2]),
          tokenId: rawPending[3],
          choice: Number(rawPending[4]),
          createdAt: rawPending[5]
        };
      }

      const nextTokenState: TokenVoteState = {
        collectionId: selectedCollectionId,
        tokenId,
        hasVoted: Boolean(hasVoted),
        choice: Number(choice),
        voter: String(voter),
        votingPower: votingPower as bigint,
        pendingRequestId,
        pending
      };
      setTokenState(nextTokenState);
      return nextTokenState;
    },
    [readContract, selectedCollectionId, tokenId, tokenInputValid]
  );

  const refreshAll = useCallback(
    async (knownRequestId?: bigint) => {
      setIsRefreshing(true);
      setStatusMessage("");
      try {
        const nextMetadata = await refreshMetadata();
        await refreshCollections();
        await refreshResults(nextMetadata);
        await refreshTokenState(knownRequestId);
      } catch (error) {
        setStatusMessage(errorMessage(error));
      } finally {
        setIsRefreshing(false);
      }
    },
    [refreshCollections, refreshMetadata, refreshResults, refreshTokenState]
  );

  const runWrapperPrecheck = useCallback(async () => {
    if (!wallet?.address) {
      setPrecheck({ status: "error", message: "Connect a wallet before prechecking ownership." });
      return;
    }
    if (!tokenInputValid) {
      setPrecheck({ status: "error", message: "Enter a valid uint token ID." });
      return;
    }

    const url = buildWrapperOwnsUrl(
      APP_CONFIG.wrapperBaseUrl,
      selectedCollectionId,
      wallet.address,
      tokenId
    );
    setPrecheck({ status: "checking" });
    try {
      const response = await fetch(url, { headers: { accept: "application/json" } });
      const data = (await response.json()) as Record<string, unknown>;
      if (!response.ok) {
        throw new Error(data.error ? String(data.error) : `HTTP ${response.status}`);
      }
      setPrecheck({ status: "ok", url, data });
    } catch (error) {
      setPrecheck({ status: "error", url, message: errorMessage(error) });
    }
  }, [selectedCollectionId, tokenId, tokenInputValid, wallet?.address]);

  const getSignerContract = useCallback(async () => {
    if (!window.ethereum) {
      throw new Error("No injected EVM wallet found.");
    }
    const provider = new BrowserProvider(window.ethereum);
    const signer = await provider.getSigner();
    return new Contract(APP_CONFIG.voteContractAddress, NFT_GATED_VOTE_ABI, signer);
  }, []);

  const submitVote = useCallback(async () => {
    if (!wallet?.address) {
      await connectWallet();
      return;
    }
    if (!connectedToSomnia) {
      setStatusMessage("Switch to Somnia Shannon Testnet before submitting a vote.");
      return;
    }
    if (!tokenInputValid) {
      setStatusMessage("Enter a valid uint token ID.");
      return;
    }
    if (results?.requestValueWei && results.contractBalanceWei < results.requestValueWei) {
      setStatusMessage("The vote contract balance is below the quoted request value.");
      return;
    }

    setVoteFlow({
      status: "submitting",
      collectionId: selectedCollectionId,
      tokenId,
      choice: selectedChoice,
      message: "Waiting for wallet signature."
    });
    setStatusMessage("");

    try {
      const signerContract = await getSignerContract();
      const tx = await signerContract.vote(
        selectedCollectionId,
        BigInt(tokenId),
        selectedChoice
      );
      setVoteFlow({
        status: "submitting",
        txHash: tx.hash,
        collectionId: selectedCollectionId,
        tokenId,
        choice: selectedChoice,
        message: "Transaction submitted. Waiting for VoteRequested event."
      });
      const receipt = await tx.wait();
      let requestId: bigint | undefined;
      for (const log of receipt.logs) {
        try {
          const parsed = signerContract.interface.parseLog(log);
          if (parsed?.name === "VoteRequested") {
            requestId = parsed.args.requestId as bigint;
            break;
          }
        } catch {
          // Ignore logs emitted by other contracts in the receipt.
        }
      }

      setVoteFlow({
        status: "pending",
        txHash: tx.hash,
        requestId,
        collectionId: selectedCollectionId,
        tokenId,
        choice: selectedChoice,
        message:
          "Vote request created on Somnia Testnet. Waiting for the ownership result."
      });
      await refreshAll(requestId);
    } catch (error) {
      setVoteFlow({
        status: "error",
        collectionId: selectedCollectionId,
        tokenId,
        choice: selectedChoice,
        message: errorMessage(error)
      });
    }
  }, [
    connectWallet,
    connectedToSomnia,
    getSignerContract,
    refreshAll,
    results?.contractBalanceWei,
    results?.requestValueWei,
    selectedChoice,
    selectedCollectionId,
    tokenId,
    tokenInputValid,
    wallet?.address
  ]);

  const runAdminTransaction = useCallback(
    async (action: "void" | "cancel" | "withdraw" | "withdrawAll") => {
      if (!APP_CONFIG.enableDemoAdminTools) {
        return;
      }
      if (!connectedToSomnia) {
        setStatusMessage("Switch to Somnia Shannon Testnet before using demo admin tools.");
        return;
      }

      try {
        const signerContract = await getSignerContract();
        let tx;
        if (action === "void") {
          if (!tokenInputValid) {
            throw new Error("Enter a valid token ID to void.");
          }
          tx = await signerContract.debugOnlyVoidVote(
            selectedCollectionId,
            BigInt(tokenId)
          );
        } else if (action === "cancel") {
          if (!isUintInput(adminRequestId)) {
            throw new Error("Enter a valid request ID to cancel.");
          }
          tx = await signerContract.debugOnlyCancelPendingRequest(BigInt(adminRequestId));
        } else if (action === "withdraw") {
          if (!isAddress(adminWithdrawTo) || !adminWithdrawAmount) {
            throw new Error("Enter a recipient address and STT amount.");
          }
          tx = await signerContract.debugOnlyWithdrawSTT(
            adminWithdrawTo,
            parseEther(adminWithdrawAmount)
          );
        } else {
          if (!isAddress(adminWithdrawTo)) {
            throw new Error("Enter a recipient address.");
          }
          tx = await signerContract.debugOnlyWithdrawAllSTT(adminWithdrawTo);
        }
        setStatusMessage(`Admin transaction submitted: ${tx.hash}`);
        await tx.wait();
        await refreshAll(voteFlow.requestId);
      } catch (error) {
        setStatusMessage(errorMessage(error));
      }
    },
    [
      adminRequestId,
      adminWithdrawAmount,
      adminWithdrawTo,
      connectedToSomnia,
      getSignerContract,
      refreshAll,
      selectedCollectionId,
      tokenId,
      tokenInputValid,
      voteFlow.requestId
    ]
  );

  useEffect(() => {
    refreshWalletState().catch(() => undefined);
    refreshAll().catch(() => undefined);
  }, [refreshAll, refreshWalletState]);

  useEffect(() => {
    if (!window.ethereum?.on) {
      return undefined;
    }
    const handleAccountsChanged = () => {
      refreshWalletState().catch(() => undefined);
    };
    const handleChainChanged = () => {
      refreshWalletState().catch(() => undefined);
    };
    window.ethereum.on("accountsChanged", handleAccountsChanged);
    window.ethereum.on("chainChanged", handleChainChanged);
    return () => {
      window.ethereum?.removeListener?.("accountsChanged", handleAccountsChanged);
      window.ethereum?.removeListener?.("chainChanged", handleChainChanged);
    };
  }, [refreshWalletState]);

  useEffect(() => {
    if (voteFlow.status !== "pending") {
      return undefined;
    }
    const interval = window.setInterval(() => {
      refreshAll(voteFlow.requestId).catch(() => undefined);
    }, 7000);
    return () => window.clearInterval(interval);
  }, [refreshAll, voteFlow.requestId, voteFlow.status]);

  useEffect(() => {
    setPrecheck({ status: "idle" });
    refreshTokenState().catch(() => undefined);
  }, [refreshTokenState, selectedCollectionId]);

  useEffect(() => {
    if (
      !tokenState ||
      !voteFlow.requestId ||
      tokenState.tokenId !== voteFlow.tokenId ||
      tokenState.collectionId !== voteFlow.collectionId
    ) {
      return;
    }
    if (tokenState.hasVoted && voteFlow.status !== "accepted") {
      setVoteFlow((current) => ({
        ...current,
        status: "accepted",
        message: "Vote accepted and counted by the callback."
      }));
      return;
    }
    if (
      voteFlow.status === "pending" &&
      tokenState.pendingRequestId === voteFlow.requestId &&
      tokenState.pending &&
      !tokenState.pending.exists &&
      !tokenState.hasVoted
    ) {
      setVoteFlow((current) => ({
        ...current,
        status: "rejected",
        message:
          "The ownership check did not record this vote."
      }));
    }
  }, [
    tokenState,
    voteFlow.collectionId,
    voteFlow.requestId,
    voteFlow.status,
    voteFlow.tokenId
  ]);

  useEffect(() => {
    if (APP_CONFIG.enableDemoAdminTools) {
      readContract
        .debugAdmin()
        .then((value: string) => setAdminAddress(value))
        .catch(() => setAdminAddress(""));
    }
  }, [readContract]);

  const tokenChoiceLabel =
    tokenState && tokenState.choice > 0
      ? choiceLabelFor(flowChoices, tokenState.choice)
      : "";
  const requestValueLow = Boolean(
    results &&
      results.contractBalanceWei < results.lowBalanceThresholdWei
  );
  const flowTone =
    voteFlow.status === "accepted"
      ? "success"
      : voteFlow.status === "rejected" || voteFlow.status === "error"
        ? "danger"
        : voteFlow.status === "pending" || voteFlow.status === "submitting"
          ? "warning"
          : "muted";
  const rankedChoices = rankChoices(results?.choices || flowChoices);

  return (
    <main className="app-shell">
      <header className="site-header">
        <a className="brand-lockup" href="#top" aria-label="Cross-chain on-chain home">
          <span>
            <strong>cross-chain, but on-chain</strong>
          </span>
        </a>

        <div className="header-actions">
          {wallet?.address && (
            <div className="wallet-pill">
              <CopyLine
                value={wallet.address}
                href={buildExplorerAddressUrl(APP_CONFIG.somniaExplorerUrl, wallet.address)}
                copied={copiedValue === wallet.address}
                onCopy={copyValue}
              />
            </div>
          )}
          {wallet?.address && !connectedToSomnia && (
            <div className="network-pill warning">
              <Network size={15} />
              <span>Wrong network</span>
            </div>
          )}
          {wallet?.address && !connectedToSomnia ? (
            <button className="secondary-button compact-button" onClick={switchToSomnia}>
              Switch to Somnia Testnet
            </button>
          ) : (
            <button className="primary-button compact-button header-connect" onClick={connectWallet}>
              <Wallet size={16} />
              {wallet?.address ? "Reconnect" : "Connect wallet"}
            </button>
          )}
        </div>
      </header>

      <section className="hero-section" id="top">
        <div className="hero-backdrop" aria-hidden="true" />
        <div className="video-stage">
          <div className="video-slot">
            {videoEmbedUrl ? (
              <>
                <iframe
                  title="Somnia NFT-gated AI vote demo video"
                  src={videoEmbedUrl}
                  allow="accelerometer; autoplay; clipboard-write; encrypted-media; gyroscope; picture-in-picture; web-share"
                  allowFullScreen
                />
                <a
                  className="video-link"
                  href={APP_CONFIG.demoVideoUrl}
                  target="_blank"
                  rel="noreferrer"
                >
                  <PlayCircle size={16} />
                  Youtube
                </a>
              </>
            ) : (
              <div className="video-placeholder">
                <PlayCircle size={34} />
                <strong>Demo video coming soon</strong>
                <span>Add VITE_DEMO_VIDEO_URL to embed the walkthrough.</span>
              </div>
            )}
          </div>
        </div>

        <div className="hero-content">
          <h1>Cross-chain NFT gating</h1>
          <p className="hero-copy">
            I showcase "cross-chain, but on-chain" by implementing gating logic
            for signatures by requiring NFTs on <strong>other</strong>{" "}
            blockchains. In turn, I use my mechanism to implement a voting
            contract.
          </p>
          <p className="hero-copy">
            Below, people can only cast a vote on Testnet if Somnia agent's JSON
            API confirms that the user's address owns either Bored Apes on
            Ethereum or Quills on Somnia Mainnet. For example, the Somnia
            Testnet blockchain asks the Ethereum blockchain for the owner address
            of a given token ID.
          </p>
          <p className="hero-copy">
            Details: To use the available HTTP GET-style JSON API calls, the
            present implementation also makes use of a small wrapper I host,
            which turns the chain's ownership response into{" "}
            <a href={WRAPPER_SAMPLE_URL} target="_blank" rel="noreferrer">
              suitable GET fields
            </a>.
          </p>
          <p className="hero-copy">
            Follow me on 𝕏:{" "}
            <a href="https://x.com/ErnstKummer" target="_blank" rel="noreferrer">
              SomniaLibrarian
            </a>{" "}
            or{" "}
            <a href="https://x.com/subcountability" target="_blank" rel="noreferrer">
              nk
            </a>
            .
          </p>
        </div>
        <a className="scroll-cue" href="#vote" aria-label="Scroll to vote">
          <ArrowDown size={18} />
          <span>Scroll to vote</span>
        </a>
      </section>

      <section className="workspace-section" id="vote">
        <div className="workspace-heading">
          <div>
            <h2>Cast your NFT-gated vote</h2>
          </div>
          <p>
            Choose preference, enter NFT and token ID and submit vote.
          </p>
        </div>

        <div className="workspace-grid">
          <div className="panel vote-panel">
            <PanelHeader
              icon={<Vote />}
              title="Vote flow"
              action={
                <button className="icon-button" onClick={() => refreshAll(voteFlow.requestId)}>
                  <RefreshCw size={17} className={isRefreshing ? "spin" : ""} />
                </button>
              }
            />

            <div className="vote-question">
              <span className="label">Poll question</span>
              <strong>Topic: {metadata.question}</strong>
            </div>

            <div className="selection-section">
              <span className="label">Selection</span>
              <div className="choice-grid" role="radiogroup" aria-label="Vote choice">
                {flowChoices.map((choice) => (
                  <button
                    key={choice.choice}
                    className={`choice-button ${
                      selectedChoice === choice.choice ? "selected" : ""
                    }`}
                    type="button"
                    role="radio"
                    aria-checked={selectedChoice === choice.choice}
                    onClick={() => setSelectedChoice(choice.choice)}
                  >
                    <Bot size={20} />
                    <span>{choice.label}</span>
                  </button>
                ))}
              </div>

              <div className="collection-grid" role="radiogroup" aria-label="NFT collection">
                {activeCollections.map((collection) => (
                  <button
                    key={collection.id}
                    className={`collection-button ${
                      selectedCollectionId === collection.id ? "selected" : ""
                    }`}
                    type="button"
                    role="radio"
                    aria-checked={selectedCollectionId === collection.id}
                    onClick={() => setSelectedCollectionId(collection.id)}
                  >
                    <span className="collection-copy">
                      <span>{collection.label}</span>
                      <small>{collectionValidationLabel(collection)}</small>
                      <strong>{collection.power}x power</strong>
                    </span>
                    {COLLECTION_ICON_BY_ID[collection.id] && (
                      <img
                        className="collection-art"
                        src={COLLECTION_ICON_BY_ID[collection.id]}
                        alt=""
                        aria-hidden="true"
                      />
                    )}
                  </button>
                ))}
              </div>
            </div>

            <div className="token-submit-row">
              <label className="input-group token-input">
                <input
                  value={tokenId}
                  onChange={(event) => setTokenId(event.target.value)}
                  placeholder="Enter ID of a token you own"
                  aria-label="Token ID"
                  inputMode="numeric"
                  autoComplete="off"
                />
              </label>
              <button
                className="primary-button submit-button"
                disabled={
                  voteFlow.status === "submitting" ||
                  !wallet?.address ||
                  !connectedToSomnia ||
                  !tokenInputValid
                }
                onClick={submitVote}
              >
                {voteFlow.status === "submitting" ? (
                  <Loader2 size={18} className="spin" />
                ) : (
                  <Vote size={18} />
                )}
                Submit vote
              </button>
            </div>

            <div className="precheck-action">
              <button
                className="secondary-button compact-button"
                disabled={!wallet?.address || !tokenInputValid || precheck.status === "checking"}
                onClick={runWrapperPrecheck}
              >
                {precheck.status === "checking" ? (
                  <Loader2 size={17} className="spin" />
                ) : (
                  <ShieldCheck size={17} />
                )}
                Wrapper pre-check
              </button>
              <span>Optional ownership check before spending STT.</span>
            </div>

            {wallet?.address && !connectedToSomnia && (
              <div className="network-banner danger">
                <Network size={18} />
                <div>
                  <strong>Somnia Shannon Testnet required</strong>
                  <span>
                    Expected chain ID {APP_CONFIG.somniaChainId}
                    {wallet.chainId ? `; wallet is on ${wallet.chainId}` : "."}
                  </span>
                </div>
                <button className="secondary-button compact-button" onClick={switchToSomnia}>
                  Switch network
                </button>
              </div>
            )}

            <PrecheckPanel state={precheck} collection={selectedCollection} />

            <div className={`status-panel ${flowTone}`}>
              <FlowStatusIcon status={voteFlow.status} />
              <div>
                <strong>{voteStatusTitle(voteFlow.status)}</strong>
                <FlowStatusMessage status={voteFlow.status} message={voteFlow.message} />
                {voteFlow.txHash && (
                  <CopyLine
                    value={voteFlow.txHash}
                    href={buildExplorerTxUrl(APP_CONFIG.somniaExplorerUrl, voteFlow.txHash)}
                    copied={copiedValue === voteFlow.txHash}
                    onCopy={copyValue}
                  />
                )}
                {voteFlow.requestId !== undefined && (
                  <span className="inline-fact">Request {voteFlow.requestId.toString()}</span>
                )}
              </div>
            </div>

          </div>

          <div className="panel results-panel">
            <PanelHeader
              icon={<Trophy />}
              title="Weighted vote count"
              action={
                <button className="icon-button" onClick={() => refreshAll(voteFlow.requestId)}>
                  <RefreshCw size={17} className={isRefreshing ? "spin" : ""} />
                </button>
              }
            />

            <div className="count-list">
              {rankedChoices.map((ranked) => (
                <div
                  className={`count-row rank-${ranked.tone}`}
                  key={ranked.choice.choice}
                >
                  <span className="rank-badge">{ranked.label}</span>
                  <div className="count-copy">
                    <span>{ranked.choice.label}</span>
                    <small>
                      {ranked.tone === "empty"
                        ? "Awaiting voting power"
                        : ranked.isTied
                          ? "Tied by weighted votes"
                          : ranked.rank === 1
                            ? "Leading"
                            : "Ranked result"}
                    </small>
                  </div>
                  <strong>{ranked.choice.count.toString()}</strong>
                </div>
              ))}
            </div>

            <div className={`balance-box ${requestValueLow ? "danger" : "success"}`}>
              {requestValueLow ? <AlertTriangle size={20} /> : <CheckCircle2 size={20} />}
              <div>
                <strong>
                  Remaining contract balance: {sttAmount(results?.contractBalanceWei, 2)}
                </strong>
                <span>Accepted votings receive a 1 STT incentive.</span>
                {requestValueLow && <span>Low balance for live votes.</span>}
                <a
                  className="subtle-link"
                  href={buildExplorerAddressUrl(
                    APP_CONFIG.somniaExplorerUrl,
                    APP_CONFIG.voteContractAddress
                  )}
                  target="_blank"
                  rel="noreferrer"
                >
                  <ExternalLink size={14} />
                  View contract
                </a>
              </div>
            </div>

            <TokenStatePanel
              tokenState={tokenState}
              tokenChoiceLabel={tokenChoiceLabel}
            />
          </div>
        </div>
      </section>

      {APP_CONFIG.enableDemoAdminTools && (
        <section className="section-band">
          <details className="admin-panel">
            <summary>
              <Settings size={18} />
              Demo admin tools
            </summary>
            <div className="admin-content">
              <div className="warning-copy">
                <AlertTriangle size={20} />
                <div>
                  <strong>DEBUG / DEMO ONLY. Not production-trustless.</strong>
                  <span>
                    TODO(DEMO-REMOVE): remove debug/admin functions before any
                    production/trustless deployment.
                  </span>
                </div>
              </div>
              <div className="admin-grid">
                <ReadOnlyFact label="debugAdmin" value={adminAddress || "Unavailable"} />
                <button className="secondary-button" onClick={() => runAdminTransaction("void")}>
                  Void selected collection token vote
                </button>
                <label className="input-group">
                  <span>Pending request ID</span>
                  <input
                    value={adminRequestId}
                    onChange={(event) => setAdminRequestId(event.target.value)}
                    placeholder="request_id"
                    inputMode="numeric"
                  />
                </label>
                <button className="secondary-button" onClick={() => runAdminTransaction("cancel")}>
                  Cancel pending request
                </button>
                <label className="input-group">
                  <span>Withdraw recipient</span>
                  <input
                    value={adminWithdrawTo}
                    onChange={(event) => setAdminWithdrawTo(event.target.value)}
                    placeholder="0x..."
                    autoComplete="off"
                  />
                </label>
                <label className="input-group">
                  <span>Withdraw amount STT</span>
                  <input
                    value={adminWithdrawAmount}
                    onChange={(event) => setAdminWithdrawAmount(event.target.value)}
                    placeholder="0.1"
                    inputMode="decimal"
                  />
                </label>
                <button className="secondary-button" onClick={() => runAdminTransaction("withdraw")}>
                  Withdraw amount
                </button>
                <button
                  className="secondary-button danger-button"
                  onClick={() => runAdminTransaction("withdrawAll")}
                >
                  Withdraw all STT
                </button>
              </div>
            </div>
          </details>
        </section>
      )}

      {(statusMessage || copiedValue) && (
        <div className="toast" role="status">
          {copiedValue ? "Copied" : statusMessage}
        </div>
      )}
    </main>
  );
}

function PanelHeader({
  icon,
  title,
  action
}: {
  icon: ReactElement;
  title: string;
  action?: ReactNode;
}) {
  return (
    <div className="panel-header">
      <div>
        <span className="panel-icon">{icon}</span>
        <h2>{title}</h2>
      </div>
      {action}
    </div>
  );
}

function CopyLine({
  value,
  href,
  copied,
  onCopy
}: {
  value: string;
  href?: string;
  copied: boolean;
  onCopy: (value: string) => void;
}) {
  return (
    <span className="copy-line">
      <code>{shortenHex(value)}</code>
      <button className="tiny-icon-button" onClick={() => onCopy(value)} title="Copy">
        <Copy size={14} />
        <span className="sr-only">{copied ? "Copied" : "Copy"}</span>
      </button>
      {href && (
        <a href={href} target="_blank" rel="noreferrer" title="Open explorer">
          <ExternalLink size={14} />
        </a>
      )}
    </span>
  );
}

function PrecheckPanel({
  state,
  collection
}: {
  state: WrapperPrecheckState;
  collection: CollectionMetadata;
}) {
  if (state.status === "idle") {
    return null;
  }
  if (state.status === "checking") {
    return (
      <div className="precheck-box warning">
        <Loader2 size={18} className="spin" />
        <span>Checking ownership.</span>
      </div>
    );
  }
  if (state.status === "error") {
    return (
      <div className="precheck-box danger">
        <XCircle size={18} />
        <div>
          <strong>Pre-check failed</strong>
          <span>{state.message}</span>
        </div>
      </div>
    );
  }

  const ownsInt = state.data.ownsInt;
  const owns = state.data.owns;
  const votingPower = state.data.votingPower;
  const targetChain = typeof state.data.targetChain === "string" ? state.data.targetChain : collection.chain;
  const targetCollection =
    typeof state.data.targetCollection === "string" ? state.data.targetCollection : collection.contractLabel;
  const owner = typeof state.data.owner === "string" ? state.data.owner : "";
  const numericVotingPower = Number(votingPower);
  const ownsPositive =
    ownsInt === 1 ||
    ownsInt === "1" ||
    owns === true ||
    (Number.isFinite(numericVotingPower) && numericVotingPower > 0);
  return (
    <div className={`precheck-box ${ownsPositive ? "success" : "danger"}`}>
      {ownsPositive ? <CheckCircle2 size={18} /> : <XCircle size={18} />}
      <div>
        <strong>{ownsPositive ? "Owns: yes" : "Owns: no"}</strong>
        <span>Power: {Number.isFinite(numericVotingPower) ? numericVotingPower : 0}</span>
        <span>{targetCollection} · {targetChain}</span>
        {owner && <span>Current owner: {shortenHex(owner)}</span>}
      </div>
    </div>
  );
}

function FlowStatusIcon({ status }: { status: VoteFlowState["status"] }) {
  if (status === "accepted") {
    return <CheckCircle2 size={20} />;
  }
  if (status === "rejected" || status === "error") {
    return <XCircle size={20} />;
  }
  if (status === "pending" || status === "submitting") {
    return <Loader2 size={20} className="spin" />;
  }
  return <Vote size={20} />;
}

function FlowStatusMessage({
  status,
  message
}: {
  status: VoteFlowState["status"];
  message?: string;
}) {
  const copy = flowStatusCopy(status, message);
  return (
    <>
      {copy.summary && <span className="flow-message">{copy.summary}</span>}
      {copy.detail && (
        <details className="error-details">
          <summary>Raw error</summary>
          <pre>{copy.detail}</pre>
        </details>
      )}
    </>
  );
}

function voteStatusTitle(status: VoteFlowState["status"]): string {
  if (status === "accepted") {
    return "Accepted";
  }
  if (status === "rejected") {
    return "Rejected";
  }
  if (status === "error") {
    return "Transaction failed";
  }
  if (status === "pending") {
    return "Pending callback";
  }
  if (status === "submitting") {
    return "Submitting";
  }
  return "Ready";
}

function TokenStatePanel({
  tokenState,
  tokenChoiceLabel
}: {
  tokenState: TokenVoteState | null;
  tokenChoiceLabel: string;
}) {
  if (!tokenState) {
    return (
      <div className="token-box muted">
        <span className="label">Selected token status</span>
        <strong>No token selected.</strong>
      </div>
    );
  }

  const rejected =
    tokenState.pendingRequestId !== 0n &&
    tokenState.pending &&
    !tokenState.pending.exists &&
    !tokenState.hasVoted;
  const pending = tokenState.pending?.exists;
  const tone = tokenState.hasVoted ? "success" : pending ? "warning" : rejected ? "danger" : "muted";

  return (
    <div className={`token-box ${tone}`}>
      <span className="label">Selected token status</span>
      <div className="fact-grid">
        <ReadOnlyFact label="Has voted" value={
          tokenState.hasVoted
            ? "Yes"
            : pending
              ? "Pending"
              : rejected
                ? "Rejected"
            : "No"
        } />
        <ReadOnlyFact label="Choice" value={tokenChoiceLabel || "None"} />
      </div>
    </div>
  );
}

function ReadOnlyFact({ label, value }: { label: string; value: string }) {
  return (
    <div className="read-only-fact">
      <span>{label}</span>
      <strong>{value}</strong>
    </div>
  );
}
