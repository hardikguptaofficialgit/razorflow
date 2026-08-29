export interface AgentHighlightRect {
  x: number;
  y: number;
  width: number;
  height: number;
}

export interface AgentCursorPoint {
  x: number;
  y: number;
}

type VisualListener = (state: AgentVisualState) => void;

export interface AgentVisualState {
  cursor: AgentCursorPoint | null;
  highlight: AgentHighlightRect | null;
  cursorMoving: boolean;
}

const initialState: AgentVisualState = {
  cursor: null,
  highlight: null,
  cursorMoving: false,
};

let state: AgentVisualState = { ...initialState };
const listeners = new Set<VisualListener>();

function emit() {
  const snapshot = { ...state };
  listeners.forEach((listener) => listener(snapshot));
}

function defaultCursorPoint(): AgentCursorPoint {
  if (typeof window === "undefined") {
    return { x: 0, y: 0 };
  }
  return { x: window.innerWidth * 0.55, y: window.innerHeight * 0.45 };
}

export function subscribeAgentVisual(listener: VisualListener): () => void {
  listeners.add(listener);
  listener({ ...state });
  return () => listeners.delete(listener);
}

export function getAgentVisualState(): AgentVisualState {
  return { ...state };
}

export function resetAgentVisual() {
  state = { ...initialState };
  emit();
}

export function primeAgentCursor(point?: AgentCursorPoint) {
  state = {
    ...state,
    cursor: point ?? defaultCursorPoint(),
    cursorMoving: false,
  };
  emit();
}

export function moveAgentCursor(point: AgentCursorPoint, moving = true) {
  state = { ...state, cursor: point, cursorMoving: moving };
  emit();
}

export function showAgentHighlight(rect: AgentHighlightRect) {
  state = { ...state, highlight: rect };
  emit();
}

export function clearAgentHighlight() {
  state = { ...state, highlight: null };
  emit();
}

export function elementVisualTarget(element: HTMLElement): {
  rect: AgentHighlightRect;
  point: AgentCursorPoint;
} {
  const rect = element.getBoundingClientRect();
  const width = Math.max(rect.width, 1);
  const height = Math.max(rect.height, 1);
  const padX = Math.min(8, width * 0.15);
  const padY = Math.min(8, height * 0.15);
  return {
    rect: {
      x: rect.left,
      y: rect.top,
      width: rect.width,
      height: rect.height,
    },
    point: {
      x: rect.left + padX + (width - padX * 2) * 0.5,
      y: rect.top + padY + (height - padY * 2) * 0.5,
    },
  };
}

function sleep(ms: number): Promise<void> {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

export async function animateAgentCursorTo(
  point: AgentCursorPoint,
  durationMs = 320,
): Promise<void> {
  const from = state.cursor ?? defaultCursorPoint();
  const frames = Math.max(14, Math.round(durationMs / 16));

  for (let frame = 1; frame <= frames; frame += 1) {
    const progress = frame / frames;
    const eased = progress < 0.5
      ? 4 * progress ** 3
      : 1 - (-2 * progress + 2) ** 3 / 2;
    moveAgentCursor(
      {
        x: from.x + (point.x - from.x) * eased,
        y: from.y + (point.y - from.y) * eased,
      },
      frame < frames,
    );
    await sleep(durationMs / frames);
  }
  moveAgentCursor(point, false);
}
