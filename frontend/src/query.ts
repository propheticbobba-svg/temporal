import { QueryClient, useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useCallback, useEffect, useState } from "react";

import { buildWorkspaceGraph, searchSources, sourceCards, sourceCategories } from "./graph";
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
  recent: () => ["places", "recent"] as const,
};

const RECENT_KEY = "temporal.recent";
const RECENT_LIMIT = 8;

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

export interface SourceFilter {
  query: string;
  category: string | null;
}

export type WorkspaceView = "graph" | "sources" | "table" | "overview";

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

export function usePlaceSources(address: string | null, filter: SourceFilter) {
  return useQuery({
    queryKey: keys.place(address ?? ""),
    queryFn: () => fetchPlace(address!),
    enabled: Boolean(address),
    select: (place) => {
      const cards = sourceCards(place.brief);
      return {
        cards: searchSources(cards, filter.query, filter.category),
        total: cards.length,
        categories: sourceCategories(cards),
      };
    },
  });
}

export function useRecentPlaces() {
  return useQuery({
    queryKey: keys.recent(),
    queryFn: readRecent,
    staleTime: Infinity,
    gcTime: Infinity,
  });
}

export function useRememberPlace() {
  const client = useQueryClient();

  return useMutation({
    mutationFn: async (address: string) => address,
    onSuccess: (address) => {
      const next = remember(client.getQueryData<string[]>(keys.recent()) ?? readRecent(), address);
      persist(next);
      client.setQueryData(keys.recent(), next);
    },
  });
}

export function usePlaceSession() {
  const [draft, setDraft] = useState("");
  const [address, setAddress] = useState<string | null>(null);
  const place = usePlaceQuery(address);
  const recent = useRecentPlaces();
  const remember = useRememberPlace();

  useEffect(() => {
    const resolved = place.data?.location.address;
    if (resolved) {
      remember.mutate(resolved);
    }
  }, [place.data?.location.address, remember.mutate]);

  const open = useCallback((value: string) => {
    const trimmed = value.trim();
    if (!trimmed) {
      return;
    }
    setDraft(trimmed);
    setAddress(trimmed);
  }, []);

  const reset = useCallback(() => {
    setAddress(null);
    setDraft("");
  }, []);

  return {
    draft,
    setDraft,
    address: place.data?.location.address ?? address,
    history: recent.data ?? [],
    open,
    reset,
    place: place.data,
    isLoading: place.isLoading,
    error: place.isError ? errorMessage(place.error) : null,
  };
}

export function useWorkspace(address: string | undefined) {
  const [view, setView] = useState<WorkspaceView>("graph");
  const [sourceFocus, setSourceFocus] = useState<string | null>(null);

  useEffect(() => {
    setView("graph");
    setSourceFocus(null);
  }, [address]);

  return {
    view,
    sourceFocus,
    openSources: (focus?: string) => {
      setSourceFocus(focus ?? null);
      setView("sources");
    },
    changeView: (next: WorkspaceView) => {
      setSourceFocus(null);
      setView(next);
    },
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

function readRecent(): string[] {
  try {
    const raw = window.localStorage.getItem(RECENT_KEY);
    if (!raw) {
      return [];
    }
    const parsed: unknown = JSON.parse(raw);
    return Array.isArray(parsed) ? parsed.filter((item): item is string => typeof item === "string") : [];
  } catch {
    return [];
  }
}

function remember(history: string[], address: string): string[] {
  if (history[0] === address) {
    return history;
  }
  return [address, ...history.filter((item) => item !== address)].slice(0, RECENT_LIMIT);
}

function persist(history: string[]): void {
  window.localStorage.setItem(RECENT_KEY, JSON.stringify(history));
}
