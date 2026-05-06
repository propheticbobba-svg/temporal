import { useCallback, useEffect, useMemo, useState } from "react";

const LOADING_STEPS = [
  "resolving address...",
  "fetching signals...",
  "building brief...",
];

async function parseApiError(response) {
  const fallback = `Request failed with status ${response.status}`;

  try {
    const data = await response.json();
    return data.detail || data.message || fallback;
  } catch {
    return fallback;
  }
}

async function postJson(path, body) {
  const response = await fetch(path, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify(body),
  });

  if (!response.ok) {
    const message = await parseApiError(response);
    const error = new Error(message);
    error.status = response.status;
    throw error;
  }

  return response.json();
}

export function useBrief() {
  const [brief, setBrief] = useState(null);
  const [location, setLocation] = useState(null);
  const [error, setError] = useState(null);
  const [isLoading, setIsLoading] = useState(false);
  const [loadingStepIndex, setLoadingStepIndex] = useState(0);

  useEffect(() => {
    if (!isLoading) {
      return undefined;
    }

    const intervalId = window.setInterval(() => {
      setLoadingStepIndex((index) => (index + 1) % LOADING_STEPS.length);
    }, 1100);

    return () => window.clearInterval(intervalId);
  }, [isLoading]);

  const reset = useCallback(() => {
    setBrief(null);
    setLocation(null);
    setError(null);
    setIsLoading(false);
    setLoadingStepIndex(0);
  }, []);

  const submitAddress = useCallback(async (address) => {
    const trimmedAddress = address.trim();

    if (!trimmedAddress) {
      setError({
        message: "Enter an address to build a brief.",
        status: 422,
      });
      return;
    }

    setBrief(null);
    setLocation(null);
    setError(null);
    setIsLoading(true);
    setLoadingStepIndex(0);

    try {
      const resolvedLocation = await postJson("/location", {
        address: trimmedAddress,
      });
      setLocation(resolvedLocation);
      setLoadingStepIndex(1);

      const report = await postJson("/brief", {
        address: resolvedLocation.address || trimmedAddress,
      });
      setLoadingStepIndex(2);
      setBrief(report);
    } catch (requestError) {
      setBrief(null);
      setLocation(null);
      setError({
        message: requestError.message,
        status: requestError.status,
      });
    } finally {
      setIsLoading(false);
    }
  }, []);

  const loadingStep = useMemo(
    () => LOADING_STEPS[loadingStepIndex],
    [loadingStepIndex],
  );

  return {
    submitAddress,
    brief,
    location,
    isLoading,
    loadingStep,
    error,
    reset,
  };
}
