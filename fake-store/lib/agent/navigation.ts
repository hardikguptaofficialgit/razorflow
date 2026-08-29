/** Client-side navigation hook for the agent (avoids full reload / WS disconnect). */

let navigateFn: ((url: string) => void) | null = null;

export function registerAgentNavigate(fn: (url: string) => void): () => void {
  navigateFn = fn;
  return () => {
    if (navigateFn === fn) {
      navigateFn = null;
    }
  };
}

export function agentNavigate(url: string): boolean {
  if (!navigateFn) {
    return false;
  }
  try {
    const target = new URL(url, window.location.origin);
    navigateFn(target.pathname + target.search + target.hash);
    return true;
  } catch {
    return false;
  }
}
