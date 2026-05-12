export type RepositorySummary = {
  id: number;
  github_repo_id: number;
  owner: string;
  name: string;
  full_name: string;
  default_branch: string;
  private: boolean;
  installation_id: number | null;
};

export type InstallationSummary = {
  id: number;
  github_installation_id: number;
  account_login: string;
  account_type: string;
  repositories: RepositorySummary[];
};

export type RunSummary = {
  id: number;
  repository_id: number | null;
  repository: RepositorySummary | { id?: number; full_name: string; default_branch?: string } | null;
  issue_number: number | null;
  issue_title: string;
  issue_url: string;
  comment_url: string;
  pull_request_url: string;
  pull_request_number: number | null;
  command: string;
  status: string;
  trigger_actor: string;
  created_at: string;
  updated_at: string;
};

export type GitHubUserSummary = {
  login: string;
  avatar_url: string;
  html_url: string;
};

export type IssueSummary = {
  id: number;
  number: number;
  title: string;
  body: string;
  state: string;
  html_url: string;
  comments: number;
  labels: Array<{ name: string; color: string }>;
  user: GitHubUserSummary | null;
  created_at: string;
  updated_at: string;
};

export type IssueComment = {
  id: number;
  body: string;
  html_url: string;
  user: GitHubUserSummary | null;
  created_at: string;
  updated_at: string;
};
