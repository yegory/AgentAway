"use client";

import { Show, SignInButton, SignUpButton, UserButton } from "@clerk/nextjs";
import { CLERK_ENABLED } from "../lib/api";

export function AuthActions() {
  if (!CLERK_ENABLED) {
    return <span className="pill warn">Dev auth</span>;
  }

  return <ClerkAuthActions />;
}

function ClerkAuthActions() {
  return (
    <>
      <Show when="signed-out">
        <SignInButton mode="modal">
          <button className="nav-link" type="button">
            Sign in
          </button>
        </SignInButton>
        <SignUpButton mode="modal">
          <button className="primary-action compact-action" type="button">
            Sign up
          </button>
        </SignUpButton>
      </Show>
      <Show when="signed-in">
        <UserButton />
      </Show>
    </>
  );
}
