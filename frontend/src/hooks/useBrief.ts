import { useCallback, useState } from "react";

import { createBrief, isRequestError, resolveLocation } from "../lib/api";
import type { ApiError, Brief, Location } from "../types/api";

const HISTORY_KEY = "temporal.recent";
const HISTORY_LIMIT = 8;

function loadHistory(): string[] {
  try {
    const raw = window.localStorage.getItem(HISTORY_KEY);
    if (!raw) {
      return [];
    }
    const parsed: unknown = JSON.parse(raw);
    return Array.isArray(parsed)
      ? parsed.filter((item): item is string => typeof item === "string")
      : [];
  } catch {
    return [];
  }
}

function persistHistory(history: string[]): void {
  window.localStorage.setItem(HISTORY_KEY, JSON.stringify(history));
}

export function useBrief() {
  const [brief, setBrief] = useState<Brief | null>(null);
  const [location, setLocation] = useState<Location | null>(null);
  const [error, setError] = useState<ApiError | null>(null);
  const [isLoading, setIsLoading] = useState(false);
  const [history, setHistory] = useState<string[]>(loadHistory);

  const reset = useCallback(() => {
    setBrief(null);
    setLocation(null);
    setError(null);
    setIsLoading(false);
  }, []);

  const submitAddress = useCallback(async (address: string) => {
    const trimmedAddress = address.trim();

    if (!trimmedAddress) {
      setError({ message: "Enter an address.", status: 422 });
      return;
    }

    setBrief(null);
    setLocation(null);
    setError(null);
    setIsLoading(true);

    try {
      const resolved = await resolveLocation(trimmedAddress);
      setLocation(resolved);
      const report = await createBrief(resolved.address || trimmedAddress);
      setBrief(report);
      setHistory((current) => {
        const next = [
          resolved.address,
          ...current.filter((item) => item !== resolved.address),
        ].slice(0, HISTORY_LIMIT);
        persistHistory(next);
        return next;
      });
    } catch (requestError) {
      setBrief(null);
      setLocation(null);
      setError({
        message: isRequestError(requestError)
          ? requestError.message
          : "Unable to build a brief for this address.",
        status: isRequestError(requestError) ? requestError.status : undefined,
      });
    } finally {
      setIsLoading(false);
    }
  }, []);

  return {
    submitAddress,
    brief,
    location,
    isLoading,
    error,
    history,
    reset,
  };
}
