import type { Brief, Location } from "../types/api";

class RequestError extends Error {
  status?: number;

  constructor(message: string, status?: number) {
    super(message);
    this.name = "RequestError";
    this.status = status;
  }
}

async function parseApiError(response: Response): Promise<string> {
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

async function postJson<T>(path: string, body: unknown): Promise<T> {
  const response = await fetch(path, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });

  if (!response.ok) {
    throw new RequestError(await parseApiError(response), response.status);
  }

  return (await response.json()) as T;
}

export function resolveLocation(address: string): Promise<Location> {
  return postJson<Location>("/location", { address });
}

export function createBrief(address: string): Promise<Brief> {
  return postJson<Brief>("/brief", { address });
}

export function isRequestError(error: unknown): error is RequestError {
  return error instanceof RequestError;
}
