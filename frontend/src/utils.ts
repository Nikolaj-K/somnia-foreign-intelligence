export type ChoiceCount = {
  choice: number;
  label: string;
  count: bigint;
};

export type LeaderState =
  | { kind: "none"; label: "No votes yet."; votes: 0n; tiedChoices: [] }
  | {
      kind: "tie";
      label: "Tie";
      votes: bigint;
      tiedChoices: ChoiceCount[];
    }
  | {
      kind: "leader";
      label: string;
      votes: bigint;
      choice: ChoiceCount;
      tiedChoices: [];
    };

export function shortenHex(value: string, head = 6, tail = 4): string {
  if (!value) {
    return "";
  }
  if (value.length <= head + tail + 3) {
    return value;
  }
  return `${value.slice(0, head)}...${value.slice(-tail)}`;
}

export function buildExplorerAddressUrl(
  explorerBaseUrl: string,
  address: string
): string {
  return `${explorerBaseUrl.replace(/\/+$/, "")}/address/${address}`;
}

export function buildExplorerTxUrl(
  explorerBaseUrl: string,
  txHash: string
): string {
  return `${explorerBaseUrl.replace(/\/+$/, "")}/tx/${txHash}`;
}

export function buildWrapperOwnsUrl(
  wrapperBaseUrl: string,
  collectionId: number,
  wallet: string,
  tokenId: string
): string {
  const cleanedBaseUrl = wrapperBaseUrl.replace(/\/+$/, "");
  const url = new URL(
    cleanedBaseUrl.endsWith("/owns") ? cleanedBaseUrl : `${cleanedBaseUrl}/owns`
  );
  url.searchParams.set("collectionId", String(collectionId));
  url.searchParams.set("wallet", wallet);
  url.searchParams.set("tokenId", tokenId);
  return url.toString();
}

export function isUintInput(value: string): boolean {
  return /^(0|[1-9]\d*)$/.test(value.trim());
}

export function calculateLeader(choices: ChoiceCount[]): LeaderState {
  const maxVotes = choices.reduce<bigint>(
    (currentMax, choice) => (choice.count > currentMax ? choice.count : currentMax),
    0n
  );
  if (maxVotes === 0n) {
    return {
      kind: "none",
      label: "No votes yet.",
      votes: 0n,
      tiedChoices: []
    };
  }

  const tiedChoices = choices.filter((choice) => choice.count === maxVotes);
  if (tiedChoices.length > 1) {
    return {
      kind: "tie",
      label: "Tie",
      votes: maxVotes,
      tiedChoices
    };
  }

  return {
    kind: "leader",
    label: tiedChoices[0].label,
    votes: maxVotes,
    choice: tiedChoices[0],
    tiedChoices: []
  };
}

export function parseYoutubeEmbedUrl(value: string): string | null {
  if (!value || value.includes("REPLACE_ME")) {
    return null;
  }

  try {
    const url = new URL(value);
    if (url.hostname === "youtu.be") {
      const id = url.pathname.split("/").filter(Boolean)[0];
      return id ? `https://www.youtube.com/embed/${id}` : null;
    }
    if (url.hostname.includes("youtube.com")) {
      const id = url.searchParams.get("v");
      return id ? `https://www.youtube.com/embed/${id}` : null;
    }
  } catch {
    return null;
  }

  return null;
}

export function formatTimestamp(seconds: bigint | number): string {
  const numericSeconds = Number(seconds);
  if (!Number.isFinite(numericSeconds) || numericSeconds <= 0) {
    return "";
  }
  return new Date(numericSeconds * 1000).toLocaleString();
}
