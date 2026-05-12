export type ApiTokenGrantSummary = {
  status: string;
};

export type TokenRevealState = {
  access_token?: string;
  refresh_token?: string;
} | null;

export const API_SCOPE_COPY: Record<string, { label: string; description: string }> = {
  "account:read": { label: "Account", description: "Profile metadata" },
  "repos:read": { label: "Repositories", description: "Linked repo list" },
  "issues:read": { label: "Issues read", description: "Issue and comment reads" },
  "issues:write": { label: "Issues write", description: "Create issues and comments" },
  "commands:write": { label: "Commands", description: "Post agent commands" },
  "runs:read": { label: "Runs read", description: "Run inbox and detail" },
  "runs:write": { label: "Runs write", description: "Stop active runs" },
};

export function nextScopeSelection(current: string[], scope: string) {
  return current.includes(scope)
    ? current.filter((item) => item !== scope)
    : [...current, scope];
}

export function countActiveTokens(tokens: ApiTokenGrantSummary[]) {
  return tokens.filter((token) => token.status === "active").length;
}

export function hasTokenReveal(reveal: TokenRevealState) {
  return Boolean(reveal?.access_token && reveal.refresh_token);
}
