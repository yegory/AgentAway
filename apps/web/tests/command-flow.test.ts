import assert from "node:assert/strict";
import test from "node:test";
import {
  buildCommandText,
  commandFromText,
  commandNeedsConfirmation,
} from "../lib/commands";
import {
  countActiveTokens,
  hasTokenReveal,
  nextScopeSelection,
} from "../lib/security";

test("builds a guided plan command with constraints", () => {
  assert.equal(
    buildCommandText("plan", ["add tests", "max 2 files"]),
    "/plan add tests max 2 files",
  );
});

test("raw command entry is preserved for power users", () => {
  assert.equal(
    buildCommandText("plan", ["add tests"], "/agent fix only touch frontend files"),
    "/agent fix only touch frontend files",
  );
  assert.equal(commandFromText("/agent fix only touch frontend files"), "fix");
});

test("implementation commands require confirmation", () => {
  assert.equal(commandNeedsConfirmation("fix"), true);
  assert.equal(commandNeedsConfirmation("proceed"), true);
  assert.equal(commandNeedsConfirmation("plan"), false);
  assert.equal(commandNeedsConfirmation("plan", "/fix add tests"), true);
});

test("token scope selection toggles without mutating the original list", () => {
  const initial = ["account:read"];
  const added = nextScopeSelection(initial, "runs:read");
  const removed = nextScopeSelection(added, "account:read");

  assert.deepEqual(initial, ["account:read"]);
  assert.deepEqual(added, ["account:read", "runs:read"]);
  assert.deepEqual(removed, ["runs:read"]);
});

test("token reveal requires both access and refresh values", () => {
  assert.equal(hasTokenReveal(null), false);
  assert.equal(hasTokenReveal({ access_token: "access" }), false);
  assert.equal(hasTokenReveal({ access_token: "access", refresh_token: "refresh" }), true);
});

test("active token count ignores revoked grants", () => {
  assert.equal(
    countActiveTokens([{ status: "active" }, { status: "revoked" }, { status: "active" }]),
    2,
  );
});
