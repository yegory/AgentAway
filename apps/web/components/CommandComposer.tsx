"use client";

import { FormEvent, useMemo, useState } from "react";
import {
  AgentCommand,
  CONSTRAINT_OPTIONS,
  buildCommandText,
  commandNeedsConfirmation,
} from "../lib/commands";
import { useApiSession } from "../lib/useApiSession";

type CommandComposerProps = {
  repositoryId: number;
  issueNumber: number;
  initialCommand?: AgentCommand;
  compact?: boolean;
  onPosted?: () => void;
};

const COMMANDS: Array<{ id: AgentCommand; label: string }> = [
  { id: "plan", label: "Plan" },
  { id: "fixplan", label: "Fix Plan" },
  { id: "proceed", label: "Proceed" },
  { id: "fix", label: "Fix" },
];

export function CommandComposer({
  repositoryId,
  issueNumber,
  initialCommand = "plan",
  compact = false,
  onPosted,
}: CommandComposerProps) {
  const session = useApiSession();
  const [command, setCommand] = useState<AgentCommand>(initialCommand);
  const [constraints, setConstraints] = useState<string[]>(["add tests", "max 2 files"]);
  const [rawMode, setRawMode] = useState(false);
  const [rawCommand, setRawCommand] = useState("");
  const [confirmed, setConfirmed] = useState(false);
  const [message, setMessage] = useState("");
  const [busy, setBusy] = useState(false);

  const preview = useMemo(
    () => buildCommandText(command, constraints, rawMode ? rawCommand : ""),
    [command, constraints, rawCommand, rawMode],
  );
  const needsConfirmation = commandNeedsConfirmation(command, rawMode ? rawCommand : "");

  function toggleConstraint(value: string) {
    setConstraints((current) =>
      current.includes(value)
        ? current.filter((item) => item !== value)
        : [...current, value],
    );
  }

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!session.ready || !session.signedIn) {
      return;
    }
    if (needsConfirmation && !confirmed) {
      setMessage("Confirm implementation before posting this command.");
      return;
    }

    setBusy(true);
    setMessage("Posting command.");
    try {
      const response = await session.fetchApi(
        `/api/repositories/${repositoryId}/issues/${issueNumber}/commands`,
        {
          method: "POST",
          body: JSON.stringify({
            command,
            constraints,
            raw_command: rawMode ? rawCommand : null,
            confirm_implementation: confirmed,
          }),
        },
      );
      setMessage(response.ok ? "Command comment posted." : "Command could not be posted.");
      if (response.ok) {
        setRawCommand("");
        setConfirmed(false);
        onPosted?.();
      }
    } catch {
      setMessage("API is unreachable.");
    } finally {
      setBusy(false);
    }
  }

  if (!session.ready) {
    return <p className="muted">Loading command controls.</p>;
  }
  if (!session.signedIn) {
    return <p className="muted">Sign in to post commands.</p>;
  }

  return (
    <form className={`command-composer ${compact ? "compact" : ""}`} onSubmit={submit}>
      <div className="segmented" role="tablist" aria-label="Agent command">
        {COMMANDS.map((item) => (
          <button
            aria-selected={command === item.id}
            className={command === item.id ? "active" : ""}
            key={item.id}
            onClick={() => {
              setCommand(item.id);
              setConfirmed(false);
            }}
            type="button"
          >
            {item.label}
          </button>
        ))}
      </div>

      <div className="check-row" aria-label="Command constraints">
        {CONSTRAINT_OPTIONS.map((constraint) => (
          <label className="check-chip" key={constraint}>
            <input
              checked={constraints.includes(constraint)}
              disabled={rawMode}
              onChange={() => toggleConstraint(constraint)}
              type="checkbox"
            />
            <span>{constraint}</span>
          </label>
        ))}
      </div>

      <label className="inline-check">
        <input checked={rawMode} onChange={(event) => setRawMode(event.target.checked)} type="checkbox" />
        <span>Raw command</span>
      </label>

      {rawMode ? (
        <label>
          <span>Power-user command</span>
          <textarea
            onChange={(event) => setRawCommand(event.target.value)}
            placeholder="/fix add tests max 2 files"
            value={rawCommand}
          />
        </label>
      ) : null}

      {needsConfirmation ? (
        <label className="confirm-box">
          <input checked={confirmed} onChange={(event) => setConfirmed(event.target.checked)} type="checkbox" />
          <span>I understand this starts an implementation attempt that must open a draft PR.</span>
        </label>
      ) : null}

      <div className="command-preview">
        <span>Will post</span>
        <code>{preview || "/plan"}</code>
      </div>

      <div className="form-actions">
        <button className="primary-action" disabled={busy} type="submit">
          {busy ? "Posting" : "Post command"}
        </button>
        {message ? <p className="muted">{message}</p> : null}
      </div>
    </form>
  );
}
