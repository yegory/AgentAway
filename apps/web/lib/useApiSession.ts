"use client";

import { useAuth } from "@clerk/nextjs";
import { apiFetch, CLERK_ENABLED } from "./api";

type ApiSession =
  | { ready: false; signedIn: false; fetchApi: typeof apiFetch }
  | { ready: true; signedIn: false; fetchApi: typeof apiFetch }
  | { ready: true; signedIn: true; fetchApi: typeof apiFetch };

export function useApiSession(): ApiSession {
  if (!CLERK_ENABLED) {
    return {
      ready: true,
      signedIn: true,
      fetchApi: (path, options = {}) => apiFetch(path, options),
    };
  }

  const { getToken, isLoaded, isSignedIn } = useAuth();
  const fetchApi: typeof apiFetch = async (path, options = {}) =>
    apiFetch(path, { ...options, token: await getToken() });

  if (!isLoaded) {
    return { ready: false, signedIn: false, fetchApi };
  }
  return { ready: true, signedIn: Boolean(isSignedIn), fetchApi };
}
