"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import {
  createEmptySession,
  loadActiveSessionId,
  loadSessions,
  saveActiveSessionId,
  saveSessions,
  statusFromPhase,
  titleFromTask,
  type AgentSession,
} from "@/lib/agent/agent-sessions";
import type { useAgentBridge } from "@/lib/agent/useAgentBridge";

type Bridge = ReturnType<typeof useAgentBridge>;

function upsertSession(
  sessions: AgentSession[],
  session: AgentSession,
): AgentSession[] {
  const index = sessions.findIndex((item) => item.id === session.id);
  if (index === -1) {
    return [session, ...sessions];
  }
  const next = [...sessions];
  next[index] = session;
  return next.sort((a, b) => b.updatedAt - a.updatedAt);
}

export function useAgentSessions(bridge: Bridge) {
  const [sessions, setSessions] = useState<AgentSession[]>([]);
  const [activeSessionId, setActiveSessionId] = useState<string | null>(null);
  const [ready, setReady] = useState(false);
  const syncingRef = useRef(false);

  useEffect(() => {
    const stored = loadSessions();
    const activeId = loadActiveSessionId();
    const fallback = stored[0] ?? createEmptySession();
    const resolvedId =
      activeId && stored.some((session) => session.id === activeId)
        ? activeId
        : fallback.id;

    const resolvedSessions =
      stored.length > 0 ? stored : upsertSession([], fallback);

    setSessions(resolvedSessions);
    setActiveSessionId(resolvedId);
    saveSessions(resolvedSessions);
    saveActiveSessionId(resolvedId);

    const active = resolvedSessions.find((session) => session.id === resolvedId);
    if (active) {
      syncingRef.current = true;
      bridge.hydrateTimeline(active.messages);
      syncingRef.current = false;
    }
    setReady(true);
    // eslint-disable-next-line react-hooks/exhaustive-deps -- bootstrap once
  }, []);

  const activeSession =
    sessions.find((session) => session.id === activeSessionId) ?? null;

  const persistActiveSession = useCallback(
    (patch: Partial<AgentSession>) => {
      if (!activeSessionId) {
        return;
      }
      setSessions((prev) => {
        const current = prev.find((session) => session.id === activeSessionId);
        if (!current) {
          return prev;
        }
        const updated: AgentSession = {
          ...current,
          ...patch,
          updatedAt: Date.now(),
        };
        const next = upsertSession(prev, updated);
        saveSessions(next);
        return next;
      });
    },
    [activeSessionId],
  );

  useEffect(() => {
    if (!ready || !activeSessionId || syncingRef.current) {
      return;
    }
    persistActiveSession({
      messages: bridge.timeline,
      status: statusFromPhase(bridge.phase),
    });
  }, [
    bridge.timeline,
    bridge.phase,
    activeSessionId,
    ready,
    persistActiveSession,
  ]);

  const createSession = useCallback(() => {
    if (bridge.runId && bridge.phase !== "idle" && bridge.phase !== "complete") {
      bridge.cancelRun();
    }

    const session = createEmptySession();
    setSessions((prev) => {
      const next = upsertSession(prev, session);
      saveSessions(next);
      return next;
    });
    setActiveSessionId(session.id);
    saveActiveSessionId(session.id);
    syncingRef.current = true;
    bridge.resetConversation();
    syncingRef.current = false;
    return session;
  }, [bridge]);

  const switchSession = useCallback(
    (sessionId: string) => {
      if (sessionId === activeSessionId) {
        return;
      }

      if (bridge.runId && bridge.phase !== "idle" && bridge.phase !== "complete") {
        bridge.cancelRun();
      }

      const target = sessions.find((session) => session.id === sessionId);
      if (!target) {
        return;
      }

      setActiveSessionId(sessionId);
      saveActiveSessionId(sessionId);
      syncingRef.current = true;
      bridge.hydrateTimeline(target.messages);
      syncingRef.current = false;
    },
    [activeSessionId, bridge, sessions],
  );

  const noteTaskStarted = useCallback(
    (task: string) => {
      if (!activeSessionId) {
        return;
      }
      persistActiveSession({
        title: titleFromTask(task),
        lastTask: task.trim(),
        status: "running",
      });
    },
    [activeSessionId, persistActiveSession],
  );

  const ensureActiveSession = useCallback(() => {
    if (activeSessionId && sessions.some((session) => session.id === activeSessionId)) {
      return activeSessionId;
    }
    const session = createEmptySession();
    setSessions((prev) => {
      const next = upsertSession(prev, session);
      saveSessions(next);
      return next;
    });
    setActiveSessionId(session.id);
    saveActiveSessionId(session.id);
    return session.id;
  }, [activeSessionId, sessions]);

  return {
    ready,
    sessions,
    activeSession,
    activeSessionId,
    createSession,
    switchSession,
    noteTaskStarted,
    ensureActiveSession,
  };
}
