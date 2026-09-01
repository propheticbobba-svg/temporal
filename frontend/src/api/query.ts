import { QueryClient, useQuery, useQueryClient } from "@tanstack/react-query";
import { useCallback, useEffect, useRef, useState } from "react";

import { buildWorkspaceGraph } from "../graph";
import type { Brief, Location } from "./types";

export const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      retry: false,
      refetchOnWindowFocus: false,
      staleTime: 30 * 60 * 1000,
      gcTime: 30 * 60 * 1000,
    },
  },
});

const keys = {
  place: (address: string) => ["place", address] as const,
};

export class RequestError extends Error {
  readonly status?: number;

  constructor(message: string, status?: number) {
    super(message);
    this.name = "RequestError";
    this.status = status;
  }
}

export interface Place {
  location: Location;
  brief: Brief;
}

export type WorkspaceView = "graph" | "overview";

export async function fetchPlace(address: string): Promise<Place> {
  const location = await postJson<Location>("/location", { address });
  const brief = await postJson<Brief>("/brief", { address: location.address || address });
  return { location, brief };
}

export function usePlaceQuery(address: string | null) {
  const client = useQueryClient();

  return useQuery({
    queryKey: keys.place(address ?? ""),
    enabled: Boolean(address),
    queryFn: async () => {
      const place = await fetchPlace(address!);
      const canonical = place.location.address;
      if (canonical && canonical !== address) {
        client.setQueryData(keys.place(canonical), place);
      }
      return place;
    },
  });
}

export function usePlaceGraph(address: string | null) {
  return useQuery({
    queryKey: keys.place(address ?? ""),
    queryFn: () => fetchPlace(address!),
    enabled: Boolean(address),
    select: (place) => buildWorkspaceGraph(place.brief),
  });
}

export function usePlaceSession() {
  const [draft, setDraft] = useState("");
  const [address, setAddress] = useState<string | null>(null);
  const [ticket, setTicket] = useState(0);
  const place = usePlaceQuery(address);

  const open = useCallback((value: string) => {
    const trimmed = value.trim();
    if (!trimmed) {
      return;
    }
    setDraft(trimmed);
    setAddress(trimmed);
    setTicket((count) => count + 1);
  }, []);

  useEffect(() => {
    if (ticket === 0 || !place.isError) {
      return;
    }
    void place.refetch();
  }, [place.isError, place.refetch, ticket]);

  const reset = useCallback(() => {
    setAddress(null);
    setDraft("");
    setTicket(0);
  }, []);

  return {
    draft,
    setDraft,
    address: place.data?.location.address ?? address,
    ticket,
    open,
    reset,
    place: place.data,
    isLoading: place.isLoading || place.isFetching,
    error: place.isError ? errorMessage(place.error) : null,
  };
}

const REVEAL_MS = 700;

export function useReveal(ticket: number, dataReady: boolean, failed: boolean): "home" | "thinking" | "ready" {
  const [stage, setStage] = useState<"home" | "thinking" | "ready">("home");
  const [armed, setArmed] = useState(0);
  const begun = useRef(0);

  useEffect(() => {
    begun.current = ticket === 0 ? 0 : Date.now();
  }, [ticket]);

  useEffect(() => {
    setArmed(ticket);
    if (ticket === 0) {
      setStage("home");
      return;
    }
    setStage("thinking");
    if (failed) {
      setStage("home");
      return;
    }
    if (!dataReady) {
      return;
    }
    const wait = Math.max(0, REVEAL_MS - (Date.now() - begun.current));
    const timer = window.setTimeout(() => setStage("ready"), wait);
    return () => window.clearTimeout(timer);
  }, [dataReady, failed, ticket]);

  if (ticket === 0 || failed) {
    return "home";
  }
  if (armed === ticket && stage === "ready" && dataReady) {
    return "ready";
  }
  return "thinking";
}

export function useWorkspace(address: string | undefined) {
  const [view, setView] = useState<WorkspaceView>("graph");

  useEffect(() => {
    setView("graph");
  }, [address]);

  return {
    view,
    openOverview: () => setView("overview"),
    changeView: setView,
  };
}

export function errorMessage(error: unknown): string {
  if (error instanceof RequestError) {
    return error.message;
  }
  if (error instanceof Error && error.message) {
    return error.message;
  }
  return "Unable to build a brief for this address.";
}

async function postJson<T>(path: string, body: unknown): Promise<T> {
  const response = await fetch(path, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!response.ok) {
    throw new RequestError(await readError(response), response.status);
  }
  return (await response.json()) as T;
}

async function readError(response: Response): Promise<string> {
  const fallback = `Request failed with status ${response.status}`;
  try {
    const data: unknown = await response.json();
    if (typeof data === "object" && data !== null) {
      const record = data as { detail?: unknown; message?: unknown };
      if (typeof record.detail === "string") {
        return record.detail;
      }
      if (typeof record.message === "string") {
        return record.message;
      }
    }
    return fallback;
  } catch {
    return fallback;
  }
}

