"use client";

import { useEffect, useMemo, useState } from "react";
import { useAgentBridge } from "@/lib/agent/useAgentBridge";
import { useAgentSessions } from "@/lib/agent/useAgentSessions";
import { resetAgentVisual } from "@/lib/agent/agent-visual";
import { isBusy } from "@/lib/agent/agent-ui-utils";
import { useAgentVoice } from "@/lib/voice/useAgentVoice";
import { AgentLauncher, AgentPanel } from "@/components/agent/AgentPanel";
import { AgentVisualOverlay } from "@/components/agent/AgentVisualOverlay";

function mapOverlayPhase(
  phase: string,
  status: string,
): "idle" | "running" | "planning" | "complete" | "error" {
  if (status !== "connected" && phase === "idle") {
    return "idle";
  }
  if (phase === "error") {
    return "error";
  }
  if (phase === "complete") {
    return "complete";
  }
  if (
    phase === "thinking" ||
    phase === "connecting" ||
    phase === "observing" ||
    phase === "verifying"
  ) {
    return "planning";
  }
  if (phase === "acting" || phase === "waiting_for_user" || phase === "payment") {
    return "running";
  }
  return "idle";
}

export function RazorflowAgent() {
  const bridge = useAgentBridge();
  const sessions = useAgentSessions(bridge);
  const [open, setOpen] = useState(false);
  const [showSessions, setShowSessions] = useState(false);
  const [task, setTask] = useState("");

  const connected = bridge.status === "connected";
  const busy = isBusy(bridge.phase);
  const hasRun = Boolean(bridge.runId);

  const showHandoff =
    bridge.phase === "waiting_for_user" ||
    bridge.phase === "payment" ||
    bridge.phase === "payment_ready";

  const agentActive =
    hasRun &&
    bridge.phase !== "idle" &&
    bridge.phase !== "complete" &&
    (bridge.phase === "acting" || bridge.phase === "observing");

  const paymentMode =
    bridge.phase === "payment"
      ? "confirm"
      : bridge.phase === "payment_ready"
        ? "ready"
        : "none";

  const voice = useAgentVoice({
    phase: bridge.phase,
    hasRun,
    connected,
    onOpenPanel: () => setOpen(true),
    onNewTask: (text) => {
      sessions.ensureActiveSession();
      sessions.noteTaskStarted(text);
      setTask(text);
      bridge.startRun(text);
      setOpen(true);
    },
    onResume: bridge.resumeRun,
  });

  useEffect(() => {
    if (busy || showHandoff) {
      setOpen(true);
    }
  }, [busy, showHandoff]);

  useEffect(() => {
    if (!hasRun && bridge.phase === "idle") {
      resetAgentVisual();
    }
  }, [hasRun, bridge.phase]);

  const overlayPhase = useMemo(
    () => mapOverlayPhase(bridge.phase, bridge.status),
    [bridge.phase, bridge.status],
  );

  function handleSubmitTask(text: string) {
    if (!connected) {
      bridge.connect();
    }
    sessions.ensureActiveSession();
    sessions.noteTaskStarted(text);

    if (bridge.awaitingClarification && bridge.lastTask) {
      const merged = `${bridge.lastTask} — ${text}`.trim();
      bridge.startRun(merged);
      return;
    }

    bridge.startRun(text);
  }

  function handleCreateSession() {
    sessions.createSession();
    setShowSessions(false);
    setTask("");
  }

  function handleSwitchSession(sessionId: string) {
    sessions.switchSession(sessionId);
    setShowSessions(false);
    setTask("");
  }

  return (
    <div
      id="razorflow-web-agent"
      data-visible="true"
      data-agent-active={agentActive ? "true" : "false"}
      data-state={voice.voicePressed ? "listening" : bridge.phase}
      data-run-phase={overlayPhase}
      data-payment-mode={paymentMode}
      data-takeover="false"
      data-voice-enabled={voice.supported ? "true" : "false"}
      data-voice-pressed={voice.voicePressed ? "true" : "false"}
      data-voice-state={voice.voiceState}
    >
      <AgentVisualOverlay />

      <div className="rf-agent-root" data-rf-agent-root>
        {open && (
          <AgentPanel
            bridge={bridge}
            voice={voice}
            sessions={sessions.sessions}
            activeSession={sessions.activeSession}
            sessionsReady={sessions.ready}
            showSessions={showSessions}
            task={task}
            onTaskChange={setTask}
            onClose={() => setOpen(false)}
            onToggleSessions={() => setShowSessions((value) => !value)}
            onCreateSession={handleCreateSession}
            onSwitchSession={handleSwitchSession}
            onSubmitTask={handleSubmitTask}
          />
        )}

        <AgentLauncher
          open={open}
          busy={busy}
          connected={connected}
          phase={bridge.phase}
          onClick={() => setOpen((value) => !value)}
        />
      </div>
    </div>
  );
}
