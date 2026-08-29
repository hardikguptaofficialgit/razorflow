"use client";

import { FormEvent, useEffect, useRef } from "react";
import type { AgentTimelineItem, AgentUiPhase } from "@/lib/agent/useAgentBridge";
import type { AgentSession } from "@/lib/agent/agent-sessions";
import { formatSessionTime } from "@/lib/agent/agent-sessions";
import {
  formatTimelineTime,
  isBusy,
  phaseLabel,
  timelineKindLabel,
  sessionStatusLabel,
} from "@/lib/agent/agent-ui-utils";
import type { useAgentVoice } from "@/lib/voice/useAgentVoice";
import { formatPrice } from "@/lib/format";
import { StoreLogo } from "@/components/StoreLogo";
import type { useAgentBridge } from "@/lib/agent/useAgentBridge";
import { formatConfigStatus } from "@/lib/agent/agent-settings";

type Bridge = ReturnType<typeof useAgentBridge>;
type Voice = ReturnType<typeof useAgentVoice>;

interface AgentPanelProps {
  bridge: Bridge;
  voice: Voice;
  sessions: AgentSession[];
  activeSession: AgentSession | null;
  sessionsReady: boolean;
  showSessions: boolean;
  task: string;
  onTaskChange: (value: string) => void;
  onClose: () => void;
  onOpenSettings: () => void;
  onToggleSessions: () => void;
  onCreateSession: () => void;
  onSwitchSession: (sessionId: string) => void;
  onSubmitTask: (task: string) => void;
}

function ConnectionBanner({ bridge }: { bridge: Bridge }) {
  if (bridge.status === "connected") {
    return null;
  }

  const isConnecting = bridge.status === "connecting";

  return (
    <div
      className={`rf-agent-banner${isConnecting ? "" : " rf-agent-banner--error"}`}
    >
      {isConnecting ? (
        "Connecting to agent backend…"
      ) : (
        <>
          Agent offline — start backend on port 8765, then{" "}
          <button type="button" onClick={bridge.connect}>
            retry
          </button>
        </>
      )}
    </div>
  );
}

function TimelineEntry({ item }: { item: AgentTimelineItem }) {
  if (item.kind === "info") {
    return (
      <div className="rf-agent-timeline__row rf-agent-timeline__row--user">
        <div className="rf-agent-timeline__user">{item.text}</div>
      </div>
    );
  }

  if (item.kind === "assistant") {
    return (
      <div className="rf-agent-timeline__row rf-agent-timeline__row--assistant">
        <div className="rf-agent-timeline__assistant">{item.text}</div>
      </div>
    );
  }

  return (
    <div className={`rf-agent-timeline__row rf-agent-timeline__row--${item.kind}`}>
      <div className="rf-agent-timeline__event">
        <div className="rf-agent-timeline__meta">
          <span className="rf-agent-timeline__kind">
            {timelineKindLabel(item.kind)}
          </span>
          <time dateTime={new Date(item.at).toISOString()}>
            {formatTimelineTime(item.at)}
          </time>
        </div>
        <p className="rf-agent-timeline__text">{item.text}</p>
      </div>
    </div>
  );
}

function HandoffCard({
  bridge,
}: {
  bridge: Bridge;
}) {
  if (bridge.phase === "waiting_for_user") {
    return (
      <div className="rf-agent-handoff">
        <p className="rf-agent-handoff__label">Handoff required</p>
        <p className="rf-agent-handoff__text">
          {bridge.waitingMessage ||
            "Complete the step in the store, then resume."}
        </p>
        <div className="rf-agent-handoff__actions">
          <button
            type="button"
            className="rf-agent-btn rf-agent-btn--ghost"
            onClick={bridge.cancelRun}
            data-rf-interactive
          >
            Cancel
          </button>
          <button
            type="button"
            className="rf-agent-btn"
            onClick={bridge.resumeRun}
            data-rf-interactive
          >
            Resume
          </button>
        </div>
      </div>
    );
  }

  if (bridge.phase === "payment" && bridge.paymentProposal) {
    return (
      <div className="rf-agent-handoff">
        <p className="rf-agent-handoff__label">Confirm payment</p>
        <p className="rf-agent-handoff__title">{bridge.paymentProposal.title}</p>
        <p className="rf-agent-handoff__text">
          {bridge.paymentProposal.description}
        </p>
        <p className="rf-agent-handoff__amount">
          {formatPrice(bridge.paymentProposal.amountPaise / 100)}
        </p>
        <div className="rf-agent-handoff__actions">
          <button
            type="button"
            className="rf-agent-btn rf-agent-btn--ghost"
            onClick={bridge.declinePayment}
            data-rf-interactive
          >
            Cancel
          </button>
          <button
            type="button"
            className="rf-agent-btn"
            onClick={bridge.confirmPayment}
            data-rf-interactive
          >
            Create link
          </button>
        </div>
      </div>
    );
  }

  if (bridge.phase === "payment_ready" && bridge.paymentLinkUrl) {
    return (
      <div className="rf-agent-handoff rf-agent-handoff--success">
        <p className="rf-agent-handoff__label">Payment ready</p>
        <p className="rf-agent-handoff__text">
          {bridge.paymentReadyDescription || "Your payment link is ready."}
        </p>
        {bridge.paymentReadyAmountPaise != null && (
          <p className="rf-agent-handoff__amount">
            {formatPrice(bridge.paymentReadyAmountPaise / 100)}
          </p>
        )}
        <a
          href={bridge.paymentLinkUrl}
          target="_blank"
          rel="noreferrer"
          className="rf-agent-btn rf-agent-btn--block"
          data-rf-interactive
        >
          Open payment link
        </a>
      </div>
    );
  }

  return null;
}

export function AgentPanel({
  bridge,
  voice,
  sessions,
  activeSession,
  sessionsReady,
  showSessions,
  task,
  onTaskChange,
  onClose,
  onOpenSettings,
  onToggleSessions,
  onCreateSession,
  onSwitchSession,
  onSubmitTask,
}: AgentPanelProps) {
  const listRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLInputElement>(null);
  const connected = bridge.status === "connected";
  const busy = isBusy(bridge.phase);
  const phase = phaseLabel(bridge.phase, connected);

  useEffect(() => {
    listRef.current?.scrollTo({
      top: listRef.current.scrollHeight,
      behavior: "smooth",
    });
  }, [bridge.timeline.length, bridge.phase, bridge.actionSummary, voice.toast]);

  function handleSubmit(event: FormEvent) {
    event.preventDefault();
    const trimmed = task.trim();
    if (!trimmed) {
      return;
    }
    onSubmitTask(trimmed);
    onTaskChange("");
  }

  return (
    <div className="rf-agent-panel" role="dialog" aria-label="RazorFlow agent">
      <header className="rf-agent-panel__header">
        <div className="rf-agent-panel__title-block">
          <button
            type="button"
            className="rf-agent-icon-btn"
            aria-label="Session history"
            onClick={onToggleSessions}
            data-rf-interactive
          >
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" aria-hidden>
              <path
                d="M4 6h16M4 12h16M4 18h10"
                stroke="currentColor"
                strokeWidth="1.8"
                strokeLinecap="round"
              />
            </svg>
          </button>
          <div className="rf-agent-panel__title-wrap">
            <p className="rf-agent-panel__title">
              {activeSession?.title ?? "RazorFlow"}
            </p>
            <p className="rf-agent-panel__status">
              <span
                className={`rf-agent-status-dot rf-agent-status-dot--${bridge.phase === "idle" && connected ? "idle" : bridge.phase}`}
                aria-hidden
              />
              {phase}
              {connected
                ? ` · ${formatConfigStatus(bridge.configStatus, connected)}`
                : ""}
              {busy && bridge.actionSummary ? ` · ${bridge.actionSummary}` : ""}
            </p>
          </div>
        </div>

        <div className="rf-agent-panel__actions">
          <button
            type="button"
            className="rf-agent-icon-btn"
            aria-label="Settings"
            title="Agent settings"
            onClick={onOpenSettings}
            data-rf-interactive
          >
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" aria-hidden>
              <path
                d="M12 15.5a3.5 3.5 0 1 0 0-7 3.5 3.5 0 0 0 0 7Z"
                stroke="currentColor"
                strokeWidth="1.8"
              />
              <path
                d="M19.4 13a7.8 7.8 0 0 0 .1-2l2-1.5-2-3.5-2.3.7a8 8 0 0 0-1.7-1L15 3h-6l-.5 2.7a8 8 0 0 0-1.7 1L4.5 6 2.5 9.5l2 1.5a7.8 7.8 0 0 0 0 2l-2 1.5 2 3.5 2.3-.7a8 8 0 0 0 1.7 1L9 21h6l.5-2.7a8 8 0 0 0 1.7-1l2.3.7 2-3.5-2-1.5Z"
                stroke="currentColor"
                strokeWidth="1.2"
                strokeLinejoin="round"
              />
            </svg>
          </button>
          <button
            type="button"
            className="rf-agent-icon-btn"
            aria-label="New session"
            title="New session"
            onClick={onCreateSession}
            data-rf-interactive
          >
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" aria-hidden>
              <path
                d="M12 5v14M5 12h14"
                stroke="currentColor"
                strokeWidth="1.8"
                strokeLinecap="round"
              />
            </svg>
          </button>
          {bridge.runId && bridge.phase !== "idle" && (
            <button
              type="button"
              className="rf-agent-icon-btn rf-agent-icon-btn--danger"
              onClick={bridge.cancelRun}
              data-rf-interactive
            >
              Stop
            </button>
          )}
          <button
            type="button"
            className="rf-agent-icon-btn"
            aria-label="Minimize"
            onClick={onClose}
            data-rf-interactive
          >
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" aria-hidden>
              <path
                d="M6 14l6-6 6 6"
                stroke="currentColor"
                strokeWidth="2"
                strokeLinecap="round"
                strokeLinejoin="round"
              />
            </svg>
          </button>
        </div>
      </header>

      <div className="rf-agent-panel__body">
        {showSessions && (
          <aside className="rf-agent-sessions" aria-label="Session history">
            <div className="rf-agent-sessions__head">
              <p>Sessions</p>
              <button
                type="button"
                className="rf-agent-sessions__new"
                onClick={onCreateSession}
                data-rf-interactive
              >
                New
              </button>
            </div>
            <ul className="rf-agent-sessions__list">
              {sessions.map((session) => (
                <li key={session.id}>
                  <button
                    type="button"
                    className={`rf-agent-sessions__item${
                      session.id === activeSession?.id
                        ? " rf-agent-sessions__item--active"
                        : ""
                    }`}
                    onClick={() => onSwitchSession(session.id)}
                    data-rf-interactive
                  >
                    <span className="rf-agent-sessions__item-title">
                      {session.title}
                    </span>
                    <span className="rf-agent-sessions__item-meta">
                      {formatSessionTime(session.updatedAt)}
                      {sessionStatusLabel(session.status)
                        ? ` · ${sessionStatusLabel(session.status)}`
                        : ""}
                    </span>
                  </button>
                </li>
              ))}
            </ul>
          </aside>
        )}

        <div className="rf-agent-panel__main">
          <ConnectionBanner bridge={bridge} />

          <div ref={listRef} className="rf-agent-timeline">
            {!sessionsReady ? (
              <div className="rf-agent-empty">
                <p className="rf-agent-empty__title">Loading sessions…</p>
              </div>
            ) : bridge.timeline.length === 0 ? (
              <div className="rf-agent-empty">
                <p className="rf-agent-empty__title">Shopping agent</p>
                <p className="rf-agent-empty__desc">
                  Start a task to search, compare, add to cart, or checkout.
                  Each session keeps its own history.
                </p>
              </div>
            ) : (
              bridge.timeline.map((item) => (
                <TimelineEntry key={item.id} item={item} />
              ))
            )}

            {busy && (
              <div className="rf-agent-live">
                <span className="rf-agent-live__dot" aria-hidden />
                {bridge.actionSummary || "Working on your request…"}
              </div>
            )}

            {bridge.error && (
              <div className="rf-agent-timeline__row rf-agent-timeline__row--error">
                <div className="rf-agent-timeline__event">
                  <div className="rf-agent-timeline__meta">
                    <span className="rf-agent-timeline__kind">Error</span>
                  </div>
                  <p className="rf-agent-timeline__text">{bridge.error}</p>
                </div>
              </div>
            )}

            <HandoffCard bridge={bridge} />
          </div>

          {voice.toast && (
            <div
              className={`rf-agent-voice-toast${
                voice.toast.error ? " rf-agent-voice-toast--error" : ""
              }`}
              role="status"
            >
              {voice.toast.text}
            </div>
          )}

          <form className="rf-agent-compose" onSubmit={handleSubmit}>
            {voice.supported && (
              <button
                type="button"
                className="rf-agent-compose__voice"
                aria-label="Hold to speak (Space)"
                title="Hold to speak, or hold Space"
                data-pressed={voice.voicePressed ? "true" : undefined}
                data-voice-state={voice.voiceState}
                onPointerDown={voice.onVoicePointerDown}
                onPointerUp={voice.onVoicePointerUp}
                onPointerLeave={voice.onVoicePointerLeave}
                onPointerCancel={voice.onVoicePointerCancel}
                data-rf-interactive
              >
                <svg width="16" height="16" viewBox="0 0 24 24" fill="none" aria-hidden>
                  <path
                    d="M12 14a3 3 0 0 0 3-3V6a3 3 0 1 0-6 0v5a3 3 0 0 0 3 3Z"
                    stroke="currentColor"
                    strokeWidth="1.7"
                  />
                  <path
                    d="M6 11a6 6 0 0 0 12 0M12 17v3"
                    stroke="currentColor"
                    strokeWidth="1.7"
                    strokeLinecap="round"
                  />
                </svg>
              </button>
            )}
            <input
              ref={inputRef}
              value={task}
              onChange={(event) => onTaskChange(event.target.value)}
              placeholder={
                connected
                  ? bridge.awaitingClarification
                    ? "Tell me what to shop for…"
                    : voice.supported
                      ? "Ask RazorFlow to shop… (hold Space to speak)"
                      : "Ask RazorFlow to shop…"
                  : "Connecting…"
              }
              autoComplete="off"
              data-rf-interactive
            />
            <button
              type="submit"
              className="rf-agent-compose__send"
              disabled={!task.trim()}
              aria-label="Send"
              data-rf-interactive
            >
              <svg width="16" height="16" viewBox="0 0 24 24" fill="none" aria-hidden>
                <path
                  d="m5 12 14-6-6 14-2-5-6-3Z"
                  stroke="currentColor"
                  strokeWidth="1.8"
                  strokeLinejoin="round"
                />
              </svg>
            </button>
          </form>
        </div>
      </div>
    </div>
  );
}

export function AgentLauncher({
  open,
  busy,
  connected,
  phase,
  onClick,
}: {
  open: boolean;
  busy: boolean;
  connected: boolean;
  phase: AgentUiPhase;
  onClick: () => void;
}) {
  return (
    <button
      type="button"
      className={`rf-agent-launcher${open ? " rf-agent-launcher--open" : ""}`}
      onClick={onClick}
      aria-expanded={open}
      aria-label={
        open
          ? "Close RazorFlow"
          : busy
            ? `Open RazorFlow (${phase})`
            : "Open RazorFlow"
      }
      data-agent-phase={phase}
      data-rf-interactive
    >
      {open ? (
        <svg width="18" height="18" viewBox="0 0 24 24" fill="none" aria-hidden>
          <path
            d="M7 7l10 10M17 7 7 17"
            stroke="currentColor"
            strokeWidth="2"
            strokeLinecap="round"
          />
        </svg>
      ) : (
        <>
          <span className="rf-agent-launcher__logo" aria-hidden>
            <StoreLogo size={22} className="rf-agent-launcher__logo-img rounded-md" />
          </span>
          <span className="rf-agent-launcher__label">RazorFlow</span>
          {busy && connected && (
            <span className="rf-agent-launcher__pulse" aria-hidden />
          )}
          {!connected && (
            <span className="rf-agent-launcher__offline" aria-hidden />
          )}
        </>
      )}
    </button>
  );
}
