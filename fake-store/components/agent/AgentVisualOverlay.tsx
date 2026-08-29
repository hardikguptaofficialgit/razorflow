"use client";

import { useEffect, useState } from "react";
import {
  getAgentVisualState,
  subscribeAgentVisual,
  type AgentVisualState,
} from "@/lib/agent/agent-visual";

export function AgentVisualOverlay() {
  const [visual, setVisual] = useState<AgentVisualState>(getAgentVisualState);

  useEffect(() => subscribeAgentVisual(setVisual), []);

  const cursorStyle =
    visual.cursor != null
      ? {
          transform: `translate3d(${visual.cursor.x}px, ${visual.cursor.y}px, 0)`,
        }
      : undefined;

  const highlightStyle =
    visual.highlight != null
      ? {
          left: visual.highlight.x,
          top: visual.highlight.y,
          width: visual.highlight.width,
          height: visual.highlight.height,
        }
      : undefined;

  return (
    <>
      <div className="rf-viewport-frame" aria-hidden />
      <div
        className={`rf-highlight${visual.highlight ? " rf-highlight--active" : ""}`}
        style={highlightStyle}
        aria-hidden
      />
      <div
        className={`rf-cursor${visual.cursorMoving ? " rf-cursor--moving" : ""}`}
        style={cursorStyle}
        aria-hidden
      >
        <svg
          className="rf-cursor-pointer"
          width="24"
          height="24"
          viewBox="0 0 24 24"
          fill="none"
          aria-hidden
        >
          <path
            d="M1.2 1.2 L1.2 16.8 L6.4 12.4 L10.6 20.8 L13.5 19.3 L9.3 10.9 L16.4 10.9 Z"
            fill="#ffffff"
            stroke="#000000"
            strokeWidth="1.15"
            strokeLinejoin="round"
          />
        </svg>
        <span className="rf-cursor-ring" aria-hidden />
      </div>
    </>
  );
}
