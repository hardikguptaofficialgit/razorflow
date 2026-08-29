export function formatDate(iso: string): string {
  return new Intl.DateTimeFormat("en-IN", {
    dateStyle: "medium",
    timeStyle: "short",
  }).format(new Date(iso));
}

export function formatOrderId(id: string): string {
  return id.slice(0, 8).toUpperCase();
}
