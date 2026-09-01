export function formatDate(value: string): string {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) {
    return "—";
  }

  return new Intl.DateTimeFormat("en-US", {
    day: "2-digit",
    month: "short",
    year: "numeric",
  }).format(date);
}

export function formatCoordinate(value: number | null | undefined): string | null {
  return typeof value === "number" ? value.toFixed(5) : null;
}

export function formatWhen(value: string): string {
  return /^\d{4}-\d{2}/.test(value) ? formatDate(value) : value;
}
