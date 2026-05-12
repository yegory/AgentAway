export type AgentCommand = "plan" | "fixplan" | "proceed" | "fix";

export const HIGH_RISK_COMMANDS = new Set<AgentCommand>(["proceed", "fix"]);

export const CONSTRAINT_OPTIONS = [
  "add tests",
  "max 2 files",
  "only touch frontend files",
] as const;

export function buildCommandText(
  command: AgentCommand,
  constraints: string[] = [],
  rawCommand = "",
) {
  const raw = rawCommand.trim();
  if (raw) {
    return raw;
  }

  const cleanConstraints = constraints
    .map((constraint) => constraint.trim().replace(/\s+/g, " "))
    .filter(Boolean);
  return `/${command}${cleanConstraints.length ? ` ${cleanConstraints.join(" ")}` : ""}`;
}

export function commandFromText(text: string): AgentCommand | null {
  const match = text
    .trim()
    .match(/^\/(?:agent(?:\s+([a-z][a-z-]*))?|([a-z][a-z-]*))(?:\b|$)/i);
  if (!match) {
    return null;
  }

  const command = (match[1] || match[2] || "plan").toLowerCase();
  if (command === "plan" || command === "fixplan" || command === "proceed" || command === "fix") {
    return command;
  }
  return null;
}

export function commandNeedsConfirmation(command: AgentCommand, rawCommand = "") {
  const raw = rawCommand.trim();
  const effectiveCommand = raw ? commandFromText(raw) : command;
  return effectiveCommand ? HIGH_RISK_COMMANDS.has(effectiveCommand) : false;
}
