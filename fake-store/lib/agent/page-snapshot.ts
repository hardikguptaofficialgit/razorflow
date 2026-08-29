import type { PageContext } from "@/lib/agent/bridge-protocol";
import { extractPageContext } from "@/lib/agent/page-context";

const MAX_SNAPSHOT_CHARS = 320_000;

function snapshotEnabled(): boolean {
  if (typeof window === "undefined") {
    return false;
  }
  return process.env.NEXT_PUBLIC_AGENT_SCREENSHOT !== "false";
}

function snapshotRoot(): HTMLElement | null {
  const root =
    document.querySelector<HTMLElement>(".rf-store-shell") ??
    document.querySelector<HTMLElement>("main");
  return root;
}

function shouldIncludeInSnapshot(node: Node): boolean {
  if (!(node instanceof HTMLElement)) {
    return true;
  }
  if (node.closest(".rf-agent-root, .rf-agent-panel, .rf-agent-launcher")) {
    return false;
  }
  return true;
}

/** Capture a JPEG snapshot of the store viewport for the planner LLM. */
export async function capturePageSnapshot(): Promise<string | undefined> {
  if (!snapshotEnabled()) {
    return undefined;
  }

  const root = snapshotRoot();
  if (!root) {
    return undefined;
  }

  try {
    const { toJpeg } = await import("html-to-image");
    const dataUrl = await toJpeg(root, {
      quality: 0.62,
      pixelRatio: Math.min(window.devicePixelRatio, 1.25),
      cacheBust: true,
      filter: shouldIncludeInSnapshot,
    });
    if (!dataUrl || dataUrl.length > MAX_SNAPSHOT_CHARS) {
      return undefined;
    }
    return dataUrl;
  } catch {
    return undefined;
  }
}

export async function attachPageSnapshot(
  context: PageContext,
): Promise<PageContext> {
  const screenshotDataUrl = await capturePageSnapshot();
  if (!screenshotDataUrl) {
    return context;
  }
  return { ...context, screenshotDataUrl };
}

export async function extractPageContextWithSnapshot(): Promise<PageContext> {
  return attachPageSnapshot(extractPageContext());
}
