"use client";

import { FormEvent, useState } from "react";
import { useRouter } from "next/navigation";
import {
  AgentCommand,
  CONSTRAINT_OPTIONS,
  buildCommandText,
  commandNeedsConfirmation,
} from "../lib/commands";
import { useApiSession } from "../lib/useApiSession";

type FirstCommand = "none" | AgentCommand;

export function NewIssueComposer({ repositoryId }: { repositoryId: number }) {
  const router = useRouter();
  const session = useApiSession();
  const [title, setTitle] = useState("");
  const [body, setBody] = useState("");
  const [firstCommand, setFirstCommand] = useState<FirstCommand>("none");
  const [constraints, setConstraints] = useState<string[]>(["add tests", "max 2 files"]);
  const [confirmed, setConfirmed] = useState(false);
  const [message, setMessage] = useState("");
  const [busy, setBusy] = useState(false);

  const commandPreview =
    firstCommand === "none" ? "No agent command" : buildCommandText(firstCommand, constraints);
  const needsConfirmation = firstCommand !== "none" && commandNeedsConfirmation(firstCommand);

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
      setMessage("Confirm implementation before creating this issue with a fix command.");
      return;
    }
    setBusy(true);
    setMessage("Creating issue.");
    try {
      const response = await session.fetchApi(`/api/repositories/${repositoryId}/issues`, {
        method: "POST",
        body: JSON.stringify({
          title,
          body,
          first_command: firstCommand,
          constraints,
          confirm_implementation: confirmed,
        }),
      });
      const payload = await response.json();
      if (!response.ok) {
        setMessage(payload.detail || "Issue could not be created.");
        return;
      }
      const issueNumber = payload.issue?.number;
      setMessage("Issue created.");
      if (issueNumber) {
        router.push(`/repos/${repositoryId}/issues/${issueNumber}`);
      }
    } catch {
      setMessage("API is unreachable.");
    } finally {
      setBusy(false);
    }
  }

  if (!session.ready) {
    return <p className="muted">Loading issue form.</p>;
  }
  if (!session.signedIn) {
    return <p className="muted">Sign in to create issues.</p>;
  }

  return (
    <form className="stack" onSubmit={submit}>
      <label>
        <span>Title</span>
        <input onChange={(event) => setTitle(event.target.value)} required value={title} />
      </label>
      <label>
        <span>Issue body</span>
        <textarea onChange={(event) => setBody(event.target.value)} rows={5} value={body} />
      </label>
      <label>
        <span>First command</span>
        <select
          onChange={(event) => {
            setFirstCommand(event.target.value as FirstCommand);
            setConfirmed(false);
          }}
          value={firstCommand}
        >
          <option value="none">No agent command</option>
          <option value="plan">/plan add tests max 2 files</option>
          <option value="fix">/fix add tests max 2 files</option>
        </select>
      </label>

      {firstCommand !== "none" ? (
        <>
          <div className="check-row" aria-label="Initial command constraints">
            {CONSTRAINT_OPTIONS.map((constraint) => (
              <label className="check-chip" key={constraint}>
                <input
                  checked={constraints.includes(constraint)}
                  onChange={() => toggleConstraint(constraint)}
                  type="checkbox"
                />
                <span>{constraint}</span>
              </label>
            ))}
          </div>
          {needsConfirmation ? (
            <label className="confirm-box">
              <input
                checked={confirmed}
                onChange={(event) => setConfirmed(event.target.checked)}
                type="checkbox"
              />
              <span>I understand this starts an implementation attempt that must open a draft PR.</span>
            </label>
          ) : null}
        </>
      ) : null}

      <div className="command-preview">
        <span>First comment</span>
        <code>{commandPreview}</code>
      </div>

      <div className="form-actions">
        <button className="primary-action" disabled={busy} type="submit">
          {busy ? "Creating" : "Create issue"}
        </button>
        {message ? <p className="muted">{message}</p> : null}
      </div>
    </form>
  );
}
