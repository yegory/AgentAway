"use client";

import { SignInButton, UserButton, useAuth } from "@clerk/nextjs";
import { CLERK_ENABLED } from "../lib/api";

export function AuthActions() {
  if (!CLERK_ENABLED) {
    return <span className="pill warn">Dev auth</span>;
  }

  return <ClerkAuthActions />;
}

function ClerkAuthActions() {
  const { isLoaded, isSignedIn } = useAuth();

  if (!isLoaded) {
    return <span className="pill warn">Loading</span>;
  }

  if (isSignedIn) {
    return <UserButton />;
  }

  return (
    <SignInButton mode="modal">
      <button className="nav-link" type="button">
        Sign in
      </button>
    </SignInButton>
  );
}
