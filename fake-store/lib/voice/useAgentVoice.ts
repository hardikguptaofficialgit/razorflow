"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import type { AgentUiPhase } from "@/lib/agent/useAgentBridge";
import { routeVoiceIntent } from "@/lib/voice/route-intent";
import type { RunStatusForVoice, VoiceUiState } from "@/lib/voice/types";
import { isSpaceVoiceKey, shouldIgnoreVoiceHotkey } from "@/lib/voice/voice-ptt";

interface SpeechRecognitionResultEvent {
  results: SpeechRecognitionResultList;
}

interface SpeechRecognitionErrorEvent {
  error: string;
}

interface BrowserSpeechRecognition extends EventTarget {
  continuous: boolean;
  interimResults: boolean;
  lang: string;
  maxAlternatives: number;
  onresult: ((event: SpeechRecognitionResultEvent) => void) | null;
  onerror: ((event: SpeechRecognitionErrorEvent) => void) | null;
  onend: (() => void) | null;
  start: () => void;
  stop: () => void;
  abort: () => void;
}

type SpeechRecognitionConstructor = new () => BrowserSpeechRecognition;

function getSpeechRecognition(): SpeechRecognitionConstructor | null {
  if (typeof window === "undefined") {
    return null;
  }

  const w = window as Window & {
    SpeechRecognition?: SpeechRecognitionConstructor;
    webkitSpeechRecognition?: SpeechRecognitionConstructor;
  };

  return w.SpeechRecognition ?? w.webkitSpeechRecognition ?? null;
}

function mapRunStatus(
  phase: AgentUiPhase,
  hasRun: boolean,
): RunStatusForVoice {
  if (phase === "waiting_for_user" || phase === "payment") {
    return "waiting_for_user";
  }
  if (hasRun) {
    return "active";
  }
  return "idle";
}

function collectTranscript(event: SpeechRecognitionResultEvent): string {
  let text = "";
  for (let index = 0; index < event.results.length; index += 1) {
    const result = event.results[index];
    if (result?.[0]?.transcript) {
      text += result[0].transcript;
    }
  }
  return text.trim();
}

export interface UseAgentVoiceOptions {
  phase: AgentUiPhase;
  hasRun: boolean;
  connected: boolean;
  onNewTask: (task: string) => void;
  onResume: () => void;
  onOpenPanel?: () => void;
}

export function useAgentVoice({
  phase,
  hasRun,
  connected,
  onNewTask,
  onResume,
  onOpenPanel,
}: UseAgentVoiceOptions) {
  const recognitionRef = useRef<BrowserSpeechRecognition | null>(null);
  const holdingRef = useRef(false);
  const spaceHeldRef = useRef(false);
  const transcriptRef = useRef("");
  const toastTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const startListeningRef = useRef<(source?: "button" | "keyboard") => void>(() => {});
  const stopListeningRef = useRef<() => void>(() => {});

  const [supported, setSupported] = useState(false);
  const [voiceState, setVoiceState] = useState<VoiceUiState>("idle");
  const [voicePressed, setVoicePressed] = useState(false);
  const [toast, setToast] = useState<{ text: string; error?: boolean } | null>(
    null,
  );

  const showToast = useCallback((text: string, error = false) => {
    setToast({ text, error });
    if (toastTimerRef.current) {
      clearTimeout(toastTimerRef.current);
    }
    toastTimerRef.current = setTimeout(() => {
      setToast(null);
      toastTimerRef.current = null;
    }, 2800);
  }, []);

  useEffect(() => {
    setSupported(getSpeechRecognition() !== null);
    return () => {
      if (toastTimerRef.current) {
        clearTimeout(toastTimerRef.current);
      }
      recognitionRef.current?.abort();
    };
  }, []);

  const processTranscript = useCallback(
    async (text: string) => {
      if (!text.trim()) {
        setVoiceState("idle");
        showToast("No speech detected", true);
        return;
      }

      setVoiceState("routing");
      showToast(text);

      const runStatus = mapRunStatus(phase, hasRun);
      const routed = await routeVoiceIntent(text, runStatus);

      if (routed.intent === "resume") {
        if (!hasRun) {
          setVoiceState("error");
          showToast("Nothing to resume", true);
          return;
        }
        onResume();
        showToast("Resumed");
      } else {
        if (!connected) {
          setVoiceState("error");
          showToast("Agent offline — start backend on :8765", true);
          return;
        }
        onNewTask(routed.taskText);
        showToast("Task started");
      }

      setVoiceState("idle");
    },
    [connected, hasRun, onNewTask, onResume, phase, showToast],
  );

  const ensureRecognition = useCallback(() => {
    const Ctor = getSpeechRecognition();
    if (!Ctor) {
      return null;
    }

    if (!recognitionRef.current) {
      const recognition = new Ctor();
      recognition.continuous = true;
      recognition.interimResults = true;
      recognition.lang = "en-IN";
      recognition.maxAlternatives = 1;

      recognition.onresult = (event) => {
        transcriptRef.current = collectTranscript(event);
      };

      recognition.onerror = (event) => {
        if (event.error === "no-speech" && holdingRef.current) {
          return;
        }
        setVoiceState("error");
        showToast(
          event.error === "not-allowed"
            ? "Microphone permission denied"
            : "Voice input failed",
          true,
        );
        holdingRef.current = false;
        spaceHeldRef.current = false;
        setVoicePressed(false);
      };

      recognition.onend = () => {
        if (holdingRef.current) {
          try {
            recognition.start();
          } catch {
            /* already running */
          }
          return;
        }

        const finalText = transcriptRef.current;
        transcriptRef.current = "";
        setVoicePressed(false);
        setVoiceState("transcribing");
        void processTranscript(finalText);
      };

      recognitionRef.current = recognition;
    }

    return recognitionRef.current;
  }, [processTranscript, showToast]);

  const startListening = useCallback(
    (source: "button" | "keyboard" = "button") => {
      if (!supported || holdingRef.current) {
        return;
      }

      const recognition = ensureRecognition();
      if (!recognition) {
        return;
      }

      onOpenPanel?.();
      transcriptRef.current = "";
      holdingRef.current = true;
      setVoicePressed(true);
      setVoiceState("recording");

      if (source === "keyboard") {
        showToast("Listening… release Space when done");
      }

      try {
        recognition.start();
      } catch {
        recognition.stop();
        try {
          recognition.start();
        } catch {
          setVoiceState("error");
          showToast("Could not start microphone", true);
          holdingRef.current = false;
          spaceHeldRef.current = false;
          setVoicePressed(false);
        }
      }
    },
    [ensureRecognition, onOpenPanel, showToast, supported],
  );

  const stopListening = useCallback(() => {
    if (!holdingRef.current) {
      return;
    }

    holdingRef.current = false;
    spaceHeldRef.current = false;
    setVoicePressed(false);
    setVoiceState("transcribing");
    showToast("Transcribing…");
    recognitionRef.current?.stop();
  }, [showToast]);

  useEffect(() => {
    startListeningRef.current = startListening;
    stopListeningRef.current = stopListening;
  }, [startListening, stopListening]);

  useEffect(() => {
    if (!supported) {
      return;
    }

    const onKeyDown = (event: KeyboardEvent) => {
      if (shouldIgnoreVoiceHotkey(event)) {
        return;
      }
      if (holdingRef.current) {
        event.preventDefault();
        return;
      }

      spaceHeldRef.current = true;
      event.preventDefault();
      event.stopPropagation();
      startListeningRef.current("keyboard");
    };

    const onKeyUp = (event: KeyboardEvent) => {
      if (!isSpaceVoiceKey(event)) {
        return;
      }
      if (!spaceHeldRef.current && !holdingRef.current) {
        return;
      }

      spaceHeldRef.current = false;
      event.preventDefault();
      event.stopPropagation();
      stopListeningRef.current();
    };

    const cancelHold = () => {
      if (!holdingRef.current) {
        return;
      }
      spaceHeldRef.current = false;
      stopListeningRef.current();
    };

    window.addEventListener("keydown", onKeyDown, true);
    window.addEventListener("keyup", onKeyUp, true);
    window.addEventListener("blur", cancelHold);
    document.addEventListener("visibilitychange", () => {
      if (document.hidden) {
        cancelHold();
      }
    });

    return () => {
      window.removeEventListener("keydown", onKeyDown, true);
      window.removeEventListener("keyup", onKeyUp, true);
      window.removeEventListener("blur", cancelHold);
    };
  }, [supported]);

  const onVoicePointerDown = useCallback(
    (event: { preventDefault: () => void }) => {
      event.preventDefault();
      startListening("button");
    },
    [startListening],
  );

  const onVoicePointerUp = useCallback(
    (event: { preventDefault: () => void }) => {
      event.preventDefault();
      stopListening();
    },
    [stopListening],
  );

  const onVoicePointerLeave = useCallback(
    (event: { preventDefault: () => void }) => {
      if (holdingRef.current) {
        stopListening();
      }
      event.preventDefault();
    },
    [stopListening],
  );

  return {
    supported,
    voiceState,
    voicePressed,
    toast,
    showToast,
    onVoicePointerDown,
    onVoicePointerUp,
    onVoicePointerLeave,
    onVoicePointerCancel: onVoicePointerLeave,
  };
}
