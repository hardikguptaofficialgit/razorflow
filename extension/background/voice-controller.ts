import { VOICE_INPUT_ENABLED } from "../shared/voice/config";
import { runSessionStore } from "./run-session";
import { routeVoiceIntent } from "../voice/intent-router";
import type {
  RunStatusForVoice,
  VoiceErrorCode,
  VoiceSource,
} from "../shared/voice/types";
import { requestPageContextFromActiveTab } from "../shared/messaging";

const OFFSCREEN_TARGET = "offscreen";
const OFFSCREEN_URL = "offscreen/offscreen.html";

type StartRunHandler = (
  task: string,
  runId: string,
  url?: string,
  pageContext?: Awaited<ReturnType<typeof requestPageContextFromActiveTab>>,
) => Promise<void>;

type ResumeRunHandler = (runId: string) => Promise<void>;

export class VoiceController {
  private offscreenCreating: Promise<void> | null = null;

  constructor(
    private readonly startRun: StartRunHandler,
    private readonly resumeRun: ResumeRunHandler,
    private readonly getActiveTabUrl: () => Promise<string | undefined>,
  ) {}

  isEnabled(): boolean {
    return VOICE_INPUT_ENABLED;
  }

  async ensureOffscreenDocument(): Promise<void> {
    if (!VOICE_INPUT_ENABLED) {
      return;
    }

    if (this.offscreenCreating) {
      await this.offscreenCreating;
      return;
    }

    const existing = await chrome.offscreen.hasDocument?.();
    if (existing) {
      return;
    }

    this.offscreenCreating = chrome.offscreen
      .createDocument({
        url: OFFSCREEN_URL,
        reasons: [chrome.offscreen.Reason.USER_MEDIA],
        justification: "On-device Moonshine speech-to-text for push-to-talk.",
      })
      .finally(() => {
        this.offscreenCreating = null;
      });

    await this.offscreenCreating;
  }

  async handlePttStart(source: VoiceSource): Promise<void> {
    if (!VOICE_INPUT_ENABLED) {
      this.broadcastStatus("error", source, "Voice input is disabled.", "disabled");
      return;
    }

    await this.ensureOffscreenDocument();

    await chrome.runtime.sendMessage({
      type: "VOICE_PTT_START",
      source,
      target: OFFSCREEN_TARGET,
    });
  }

  async handlePttStop(source: VoiceSource): Promise<void> {
    if (!VOICE_INPUT_ENABLED) {
      return;
    }

    await chrome.runtime.sendMessage({
      type: "VOICE_PTT_STOP",
      source,
      target: OFFSCREEN_TARGET,
    });
  }

  async handleFinalTranscript(text: string, source: VoiceSource): Promise<void> {
    this.broadcastStatus("routing", source, text);

    const snapshot = runSessionStore.getSnapshot();
    const runStatus: RunStatusForVoice = snapshot.context.status;

    try {
      const routed = await routeVoiceIntent(text, runStatus);

      if (routed.intent === "resume") {
        const runId = snapshot.context.runId;
        if (runStatus !== "waiting_for_user" || !runId) {
          this.broadcastStatus(
            "error",
            source,
            "No paused run to resume.",
            "no_run_to_resume",
          );
          return;
        }

        await this.resumeRun(runId);
        this.broadcastStatus("idle", source, "Resumed run.");
        return;
      }

      const taskText = routed.taskText.trim() || text.trim();
      const pageContext = await requestPageContextFromActiveTab();
      const url = await this.getActiveTabUrl();
      const runId = crypto.randomUUID();
      await this.startRun(taskText, runId, url, pageContext);
      this.broadcastStatus("idle", source, `Started: ${taskText}`);
    } catch (error) {
      this.broadcastStatus(
        "error",
        source,
        error instanceof Error ? error.message : "Could not route voice command.",
        "intent_failed",
      );
    }
  }

  broadcastStatus(
    state: "idle" | "loading_model" | "recording" | "transcribing" | "routing" | "error",
    source: VoiceSource,
    text?: string,
    errorCode?: VoiceErrorCode,
  ): void {
    void chrome.runtime.sendMessage({
      type: "VOICE_STATUS",
      state,
      text,
      errorCode,
      source,
    });
  }
}
