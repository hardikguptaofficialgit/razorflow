/** BYOK agent settings persisted in the browser (demo store). */

export type PlannerProvider =
  | "openrouter"
  | "groq"
  | "gemini"
  | "vercel_ai_gateway";

export interface AgentSettings {
  useByok: boolean;
  provider: PlannerProvider;
  apiKey: string;
  model: string;
  temperature: number;
  maxAgentSteps: number;
  shoppingSkillEnabled: boolean;
}

export interface AgentConfigStatus {
  mode: "server_default" | "byok";
  useByok: boolean;
  provider?: string;
  model?: string;
  temperature?: number;
  maxAgentSteps: number;
  shoppingSkillEnabled: boolean;
  message?: string;
}

export const STORAGE_KEY = "razorflow-agent-settings-v1";

export const PROVIDER_OPTIONS: Array<{
  id: PlannerProvider;
  label: string;
  models: string[];
}> = [
  {
    id: "openrouter",
    label: "OpenRouter",
    models: [
      "google/gemini-2.5-flash-lite:nitro",
      "openai/gpt-4o-mini",
      "anthropic/claude-3.5-sonnet",
    ],
  },
  {
    id: "groq",
    label: "Groq",
    models: ["openai/gpt-oss-120b", "llama-3.3-70b-versatile"],
  },
  {
    id: "gemini",
    label: "Google Gemini",
    models: ["gemini-2.5-flash", "gemini-2.0-flash"],
  },
  {
    id: "vercel_ai_gateway",
    label: "Vercel AI Gateway",
    models: ["google/gemini-2.5-flash-lite", "openai/gpt-4o-mini"],
  },
];

export const DEFAULT_SETTINGS: AgentSettings = {
  useByok: false,
  provider: "openrouter",
  apiKey: "",
  model: PROVIDER_OPTIONS[0].models[0],
  temperature: 0.05,
  maxAgentSteps: 40,
  shoppingSkillEnabled: true,
};

export function loadAgentSettings(): AgentSettings {
  if (typeof window === "undefined") {
    return { ...DEFAULT_SETTINGS };
  }
  try {
    const raw = window.localStorage.getItem(STORAGE_KEY);
    if (!raw) {
      return { ...DEFAULT_SETTINGS };
    }
    const parsed = JSON.parse(raw) as Partial<AgentSettings>;
    const provider = (parsed.provider as PlannerProvider) || DEFAULT_SETTINGS.provider;
    const providerModels =
      PROVIDER_OPTIONS.find((item) => item.id === provider)?.models ??
      PROVIDER_OPTIONS[0].models;
    return {
      useByok: Boolean(parsed.useByok),
      provider,
      apiKey: typeof parsed.apiKey === "string" ? parsed.apiKey : "",
      model:
        typeof parsed.model === "string" && parsed.model
          ? parsed.model
          : providerModels[0],
      temperature:
        typeof parsed.temperature === "number"
          ? parsed.temperature
          : DEFAULT_SETTINGS.temperature,
      maxAgentSteps:
        typeof parsed.maxAgentSteps === "number"
          ? Math.max(5, Math.min(parsed.maxAgentSteps, 200))
          : DEFAULT_SETTINGS.maxAgentSteps,
      shoppingSkillEnabled:
        typeof parsed.shoppingSkillEnabled === "boolean"
          ? parsed.shoppingSkillEnabled
          : DEFAULT_SETTINGS.shoppingSkillEnabled,
    };
  } catch {
    return { ...DEFAULT_SETTINGS };
  }
}

export function saveAgentSettings(settings: AgentSettings): void {
  if (typeof window === "undefined") {
    return;
  }
  window.localStorage.setItem(STORAGE_KEY, JSON.stringify(settings));
}

export function resetAgentSettings(): AgentSettings {
  if (typeof window !== "undefined") {
    window.localStorage.removeItem(STORAGE_KEY);
  }
  return { ...DEFAULT_SETTINGS };
}

export function getBridgeHttpUrl(): string {
  const ws =
    (typeof process !== "undefined" &&
      process.env.NEXT_PUBLIC_AGENT_WS_URL?.trim()) ||
    "ws://127.0.0.1:8765/ws";
  return ws.replace(/^ws/i, "http").replace(/\/ws\/?$/, "");
}

export function settingsToConfigurePayload(settings: AgentSettings) {
  return {
    useByok: settings.useByok,
    provider: settings.provider,
    apiKey: settings.useByok ? settings.apiKey : undefined,
    model: settings.useByok ? settings.model : undefined,
    temperature: settings.temperature,
    maxAgentSteps: settings.maxAgentSteps,
    shoppingSkillEnabled: settings.shoppingSkillEnabled,
  };
}

export async function testAgentConnection(
  settings: AgentSettings,
): Promise<{ ok: boolean; error?: string }> {
  if (!settings.useByok) {
    const response = await fetch(`${getBridgeHttpUrl()}/health`);
    if (!response.ok) {
      return { ok: false, error: "Backend is not reachable." };
    }
    return { ok: true };
  }
  if (!settings.apiKey.trim()) {
    return { ok: false, error: "Enter an API key to test BYOK." };
  }
  const response = await fetch(`${getBridgeHttpUrl()}/api/agent/llm/test`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      provider: settings.provider,
      apiKey: settings.apiKey,
      model: settings.model,
      temperature: settings.temperature,
    }),
  });
  const payload = (await response.json()) as { ok?: boolean; error?: string };
  if (!response.ok || !payload.ok) {
    return { ok: false, error: payload.error || "Connection test failed." };
  }
  return { ok: true };
}

export function formatConfigStatus(
  status: AgentConfigStatus | null,
  connected: boolean,
): string {
  if (!connected) {
    return "Offline";
  }
  if (!status) {
    return "Server default";
  }
  if (status.mode === "byok" && status.provider && status.model) {
    return `BYOK · ${status.provider} · ${status.model}`;
  }
  return "Server default LLM";
}
