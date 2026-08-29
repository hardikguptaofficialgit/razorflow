"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import type { AgentRun } from "@hardik21232323/razorflow-client";
import { getRazorFlowClient } from "@/lib/agent/agent-sdk";
import {
  createRunId,
  type PaymentLinkProposal,
  type BridgeConnectionStatus,
} from "@/lib/agent/bridge-protocol";
import {
  loadAgentSettings,
  type AgentConfigStatus,
  settingsToConfigurePayload,
} from "@/lib/agent/agent-settings";
import { primeAgentCursor, resetAgentVisual } from "@/lib/agent/agent-visual";
import { runtimePhaseToUiPhase } from "@/lib/agent/browser-environment";

export type AgentUiPhase =
  | "idle"
  | "connecting"
  | "thinking"
  | "acting"
  | "observing"
  | "waiting_for_user"
  | "payment"
  | "payment_ready"
  | "complete"
  | "error";

export interface AgentTimelineItem {
  id: string;
  at: number;
  text: string;
  kind: "info" | "assistant" | "sync" | "success" | "error" | "wait";
}

export interface AgentBridgeState {
  status: BridgeConnectionStatus;
  phase: AgentUiPhase;
  runId: string | null;
  actionSummary: string;
  timeline: AgentTimelineItem[];
  waitingMessage: string | null;
  paymentProposal: PaymentLinkProposal | null;
  paymentLinkUrl: string | null;
  paymentReadyAmountPaise: number | null;
  paymentReadyCurrency: string | null;
  paymentReadyReference: string | null;
  paymentReadyDescription: string | null;
  error: string | null;
  awaitingClarification: boolean;
  lastTask: string | null;
  syncUrl: string;
  syncStep: number;
  cursor: { x: number; y: number } | null;
  highlight: { x: number; y: number; width: number; height: number } | null;
  executorMode: "browser_use" | "extension_dom";
}

const initialState: AgentBridgeState = {
  status: "disconnected",
  phase: "idle",
  runId: null,
  actionSummary: "",
  timeline: [],
  waitingMessage: null,
  paymentProposal: null,
  paymentLinkUrl: null,
  paymentReadyAmountPaise: null,
  paymentReadyCurrency: null,
  paymentReadyReference: null,
  paymentReadyDescription: null,
  error: null,
  awaitingClarification: false,
  lastTask: null,
  syncUrl: "",
  syncStep: 0,
  cursor: null,
  highlight: null,
  executorMode: "extension_dom",
};

function pushTimeline(
  prev: AgentTimelineItem[],
  text: string,
  kind: AgentTimelineItem["kind"],
): AgentTimelineItem[] {
  const next = [
    ...prev,
    { id: `${Date.now()}-${prev.length}`, at: Date.now(), text, kind },
  ];
  return next.slice(-40);
}

export function useAgentBridge() {
  const client = useRef<ReturnType<typeof getRazorFlowClient> | null>(null);
  const activeRunRef = useRef<AgentRun | null>(null);
  const mountedRef = useRef(true);
  const hasConnectedOnceRef = useRef(false);
  const [configStatus, setConfigStatus] = useState<AgentConfigStatus | null>(null);
  const [state, setState] = useState<AgentBridgeState>(initialState);

  const getClient = useCallback(() => {
    if (!client.current) {
      client.current = getRazorFlowClient();
    }
    return client.current;
  }, []);

  const pushAgentConfig = useCallback(
    (settings = loadAgentSettings()) => {
      const sdk = getClient();
      if (!sdk.transport.isConnected()) {
        return;
      }
      sdk.configureAgent(settingsToConfigurePayload(settings));
    },
    [getClient],
  );

  const applyAgentSettings = useCallback(
    async (settings = loadAgentSettings()) => {
      if (!getClient().transport.isConnected()) {
        await getClient().connect();
      }
      pushAgentConfig(settings);
    },
    [getClient, pushAgentConfig],
  );

  const connect = useCallback(() => {
    void getClient().connect().catch(() => {
      if (!mountedRef.current) {
        return;
      }
      setState((prev) => ({
        ...prev,
        status: "disconnected",
        error: "Could not reach agent backend",
      }));
    });
  }, []);

  useEffect(() => {
    mountedRef.current = true;
    const sdk = getClient();

    const unsubs = [
      sdk.on("connection_change", ({ connected }) => {
        if (!mountedRef.current) {
          return;
        }
        setState((prev) => ({
          ...prev,
          status: connected ? "connected" : "disconnected",
          phase:
            connected && prev.phase === "connecting" ? "idle" : prev.phase,
          error: connected ? null : prev.error,
          timeline:
            connected && !hasConnectedOnceRef.current
              ? pushTimeline(
                  prev.timeline,
                  "Connected to Razorflow agent",
                  "success",
                )
              : prev.timeline,
        }));
        if (connected) {
          hasConnectedOnceRef.current = true;
          pushAgentConfig();
        }
      }),
      sdk.on("agent_config_status", (status) => {
        if (!mountedRef.current) {
          return;
        }
        setConfigStatus(status);
      }),
      sdk.on("agent_chat", ({ text }) => {
        if (!mountedRef.current || !text.trim()) {
          return;
        }
        setState((prev) => ({
          ...prev,
          timeline: pushTimeline(prev.timeline, text.trim(), "assistant"),
        }));
      }),
      sdk.on("executor_mode", ({ mode }) => {
        setState((prev) => ({ ...prev, executorMode: mode }));
      }),
      sdk.on("agent_sync", (payload) => {
        setState((prev) => ({
          ...prev,
          phase: runtimePhaseToUiPhase(payload.phase),
          actionSummary: payload.actionSummary,
          syncUrl: payload.url,
          syncStep: payload.step,
          runId: payload.runId || prev.runId,
          cursor: payload.cursor ?? prev.cursor,
          highlight: payload.highlight ?? null,
          timeline: pushTimeline(prev.timeline, payload.actionSummary, "sync"),
        }));
      }),
      sdk.on("action_started", ({ summary }) => {
        setState((prev) => ({
          ...prev,
          phase: "acting",
          actionSummary: summary,
        }));
      }),
      sdk.on("planning", () => {
        setState((prev) => ({
          ...prev,
          phase: "thinking",
          actionSummary: "Planning with AI…",
        }));
      }),
      sdk.on("recovery", ({ message }) => {
        setState((prev) => ({
          ...prev,
          phase: "thinking",
          actionSummary: message,
          timeline: pushTimeline(prev.timeline, message, "info"),
        }));
      }),
      sdk.on("needs_clarification", ({ message }) => {
        setState((prev) => ({
          ...prev,
          phase: "waiting_for_user",
          waitingMessage: message,
          awaitingClarification: true,
          highlight: null,
          timeline: pushTimeline(prev.timeline, message, "assistant"),
        }));
      }),
      sdk.on("handoff", ({ message }) => {
        setState((prev) => ({
          ...prev,
          phase: "waiting_for_user",
          waitingMessage: message,
          awaitingClarification: false,
          highlight: null,
          timeline: pushTimeline(prev.timeline, message, "wait"),
        }));
      }),
      sdk.on("payment_required", ({ proposal }) => {
        setState((prev) => ({
          ...prev,
          phase: "payment",
          paymentProposal: proposal,
          timeline: pushTimeline(
            prev.timeline,
            "Payment confirmation required",
            "wait",
          ),
        }));
      }),
      sdk.on("payment_ready", (payload) => {
        setState((prev) => ({
          ...prev,
          phase: "payment_ready",
          paymentLinkUrl: payload.url,
          paymentProposal: null,
          paymentReadyAmountPaise: payload.amountPaise,
          paymentReadyCurrency: payload.currency,
          timeline: pushTimeline(prev.timeline, "Payment link ready", "success"),
        }));
      }),
      sdk.on("completed", ({ message }) => {
        activeRunRef.current = null;
        const summary = message?.trim() || "All set!";
        setState((prev) => ({
          ...prev,
          phase: "complete",
          actionSummary: summary,
          waitingMessage: null,
          awaitingClarification: false,
          highlight: null,
          timeline: pushTimeline(prev.timeline, summary, "assistant"),
        }));
      }),
      sdk.on("failed", ({ message }) => {
        activeRunRef.current = null;
        setState((prev) => ({
          ...prev,
          phase: "error",
          error: message,
          awaitingClarification: false,
          highlight: null,
          timeline: pushTimeline(prev.timeline, message, "error"),
        }));
      }),
    ];

    setState((prev) => ({
      ...prev,
      status: "connecting",
      phase: prev.phase === "idle" ? "connecting" : prev.phase,
    }));
    connect();

    return () => {
      mountedRef.current = false;
      for (const unsub of unsubs) {
        unsub();
      }
    };
  }, [connect, getClient, pushAgentConfig]);

  const startRun = useCallback((task: string, url?: string) => {
    const runId = createRunId();
    primeAgentCursor();

    void (async () => {
      try {
        const run = await getClient().run({
          task: task.trim(),
          url,
          runId,
        });
        activeRunRef.current = run;
        setState((prev) => ({
          ...prev,
          runId,
          lastTask: task.trim(),
          phase: "thinking",
          actionSummary: "Planning with AI…",
          error: null,
          waitingMessage: null,
          awaitingClarification: false,
          paymentProposal: null,
          paymentLinkUrl: null,
          paymentReadyAmountPaise: null,
          paymentReadyCurrency: null,
          paymentReadyReference: null,
          paymentReadyDescription: null,
          cursor: { x: window.innerWidth / 2, y: window.innerHeight / 2 },
          highlight: null,
          timeline: pushTimeline(prev.timeline, task.trim(), "info"),
        }));
      } catch {
        setState((prev) => ({
          ...prev,
          error: "Agent backend is not connected. Start it on :8765.",
          phase: "error",
          timeline: pushTimeline(
            prev.timeline,
            "Not connected to agent backend",
            "error",
          ),
        }));
      }
    })();

    return runId;
  }, [getClient]);

  const resumeRun = useCallback(() => {
    const run = activeRunRef.current;
    if (!run) {
      return;
    }
    void run.resume();
    setState((prev) => ({
      ...prev,
      phase: "thinking",
      actionSummary: "Planning with AI…",
      waitingMessage: null,
      timeline: pushTimeline(prev.timeline, "Resumed", "info"),
    }));
  }, []);

  const cancelRun = useCallback(() => {
    const run = activeRunRef.current;
    if (!run) {
      return;
    }
    run.cancel();
    activeRunRef.current = null;
    setState((prev) => ({
      ...prev,
      phase: "idle",
      actionSummary: "",
      waitingMessage: null,
      paymentProposal: null,
      paymentLinkUrl: null,
      cursor: null,
      highlight: null,
      timeline: pushTimeline(prev.timeline, "Cancelled", "info"),
    }));
  }, []);

  const confirmPayment = useCallback(() => {
    activeRunRef.current?.confirmPayment();
  }, []);

  const declinePayment = useCallback(() => {
    activeRunRef.current?.declinePayment();
    setState((prev) => ({
      ...prev,
      phase: "idle",
      paymentProposal: null,
      timeline: pushTimeline(prev.timeline, "Payment declined", "info"),
    }));
  }, []);

  const resetConversation = useCallback(() => {
    activeRunRef.current = null;
    resetAgentVisual();
    setState((prev) => ({
      ...initialState,
      status: prev.status,
      executorMode: prev.executorMode,
      phase: prev.status === "connected" ? "idle" : "connecting",
    }));
  }, []);

  const hydrateTimeline = useCallback((timeline: AgentTimelineItem[]) => {
    activeRunRef.current = null;
    resetAgentVisual();
    const cleaned = timeline.map(({ id, at, text, kind }) => ({ id, at, text, kind }));
    setState((prev) => ({
      ...initialState,
      status: prev.status,
      executorMode: prev.executorMode,
      phase: prev.status === "connected" ? "idle" : "connecting",
      timeline: cleaned.slice(-40),
    }));
  }, []);

  const getRunTrace = useCallback(() => activeRunRef.current?.trace ?? null, []);

  return {
    ...state,
    configStatus,
    connect,
    startRun,
    resumeRun,
    cancelRun,
    confirmPayment,
    declinePayment,
    resetConversation,
    hydrateTimeline,
    getRunTrace,
    applyAgentSettings,
  };
}
