"use client";

import { FormEvent, useEffect, useMemo, useState } from "react";
import type { AgentConfigureOptions } from "@hardik21232323/razorflow-client";
import {
  DEFAULT_SETTINGS,
  PROVIDER_OPTIONS,
  loadAgentSettings,
  type AgentConfigStatus,
  type AgentSettings,
  type PlannerProvider,
  resetAgentSettings,
  saveAgentSettings,
  settingsToConfigurePayload,
  testAgentConnection,
} from "@/lib/agent/agent-settings";

interface AgentSettingsModalProps {
  open: boolean;
  connected: boolean;
  configStatus: AgentConfigStatus | null;
  onClose: () => void;
  onApply: (settings: AgentSettings) => Promise<void>;
}

type ActionState = "idle" | "saving" | "testing";

export function AgentSettingsModal({
  open,
  connected,
  configStatus,
  onClose,
  onApply,
}: AgentSettingsModalProps) {
  const [draft, setDraft] = useState<AgentSettings>(DEFAULT_SETTINGS);
  const [showKey, setShowKey] = useState(false);
  const [action, setAction] = useState<ActionState>("idle");
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);

  useEffect(() => {
    if (!open) {
      return;
    }
    setDraft(loadAgentSettings());
    setError(null);
    setNotice(null);
    setAction("idle");
  }, [open]);

  const providerMeta = useMemo(
    () => PROVIDER_OPTIONS.find((item) => item.id === draft.provider),
    [draft.provider],
  );

  if (!open) {
    return null;
  }

  function update<K extends keyof AgentSettings>(key: K, value: AgentSettings[K]) {
    setDraft((prev) => ({ ...prev, [key]: value }));
    setError(null);
    setNotice(null);
  }

  function handleProviderChange(provider: PlannerProvider) {
    const models =
      PROVIDER_OPTIONS.find((item) => item.id === provider)?.models ?? [];
    setDraft((prev) => ({
      ...prev,
      provider,
      model: models.includes(prev.model) ? prev.model : models[0] ?? prev.model,
    }));
    setError(null);
    setNotice(null);
  }

  async function handleSave(event?: FormEvent) {
    event?.preventDefault();
    setAction("saving");
    setError(null);
    setNotice(null);
    try {
      if (draft.useByok && !draft.apiKey.trim()) {
        throw new Error("API key is required when BYOK is enabled.");
      }
      if (draft.useByok && !draft.model.trim()) {
        throw new Error("Model is required when BYOK is enabled.");
      }
      saveAgentSettings(draft);
      await onApply(draft);
      setNotice("Settings saved.");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not save settings.");
    } finally {
      setAction("idle");
    }
  }

  async function handleTest() {
    setAction("testing");
    setError(null);
    setNotice(null);
    try {
      const result = await testAgentConnection(draft);
      if (!result.ok) {
        throw new Error(result.error || "Connection test failed.");
      }
      setNotice(
        draft.useByok
          ? "Connection successful. Your API key works."
          : "Backend reachable. Server default LLM will be used.",
      );
    } catch (err) {
      setError(err instanceof Error ? err.message : "Connection test failed.");
    } finally {
      setAction("idle");
    }
  }

  function handleReset() {
    const defaults = resetAgentSettings();
    setDraft(defaults);
    setError(null);
    setNotice("Reset to defaults. Save to apply.");
  }

  const busy = action !== "idle";

  return (
    <div className="rf-settings" role="presentation" onClick={onClose}>
      <div
        className="rf-settings__dialog"
        role="dialog"
        aria-modal="true"
        aria-labelledby="rf-settings-title"
        onClick={(event) => event.stopPropagation()}
      >
        <header className="rf-settings__header">
          <div>
            <h2 id="rf-settings-title">Agent settings</h2>
            <p className="rf-settings__subtitle">
              Bring your own API key or use the server default configuration.
            </p>
          </div>
          <button
            type="button"
            className="rf-settings__close"
            aria-label="Close settings"
            onClick={onClose}
          >
            ×
          </button>
        </header>

        <div className="rf-settings__status">
          <span
            className={`rf-settings__status-dot${connected ? " rf-settings__status-dot--on" : ""}`}
            aria-hidden
          />
          <div>
            <p className="rf-settings__status-label">
              {connected ? "Connected to backend" : "Backend offline"}
            </p>
            <p className="rf-settings__status-meta">
              {configStatus?.message ||
                (configStatus?.mode === "byok"
                  ? `Using BYOK · ${configStatus.provider ?? draft.provider}`
                  : "Using server default LLM")}
            </p>
          </div>
        </div>

        <form className="rf-settings__form" onSubmit={handleSave}>
          <section className="rf-settings__section">
            <h3>LLM provider</h3>
            <label className="rf-settings__field">
              <span>Provider</span>
              <select
                value={draft.provider}
                onChange={(event) =>
                  handleProviderChange(event.target.value as PlannerProvider)
                }
              >
                {PROVIDER_OPTIONS.map((option) => (
                  <option key={option.id} value={option.id}>
                    {option.label}
                  </option>
                ))}
              </select>
            </label>

            <label className="rf-settings__toggle">
              <input
                type="checkbox"
                checked={draft.useByok}
                onChange={(event) => update("useByok", event.target.checked)}
              />
              <span>Use my API key (BYOK)</span>
            </label>

            {draft.useByok && (
              <>
                <label className="rf-settings__field">
                  <span>API key</span>
                  <div className="rf-settings__secret">
                    <input
                      type={showKey ? "text" : "password"}
                      value={draft.apiKey}
                      onChange={(event) => update("apiKey", event.target.value)}
                      placeholder="sk-…"
                      autoComplete="off"
                      spellCheck={false}
                    />
                    <button
                      type="button"
                      className="rf-settings__ghost"
                      onClick={() => setShowKey((value) => !value)}
                    >
                      {showKey ? "Hide" : "Show"}
                    </button>
                  </div>
                </label>

                <label className="rf-settings__field">
                  <span>Model</span>
                  <input
                    list="rf-settings-models"
                    value={draft.model}
                    onChange={(event) => update("model", event.target.value)}
                    placeholder={providerMeta?.models[0] ?? "model id"}
                  />
                  <datalist id="rf-settings-models">
                    {providerMeta?.models.map((model) => (
                      <option key={model} value={model} />
                    ))}
                  </datalist>
                </label>
              </>
            )}
          </section>

          <section className="rf-settings__section">
            <h3>Agent behavior</h3>
            <label className="rf-settings__field">
              <span>Temperature ({draft.temperature.toFixed(2)})</span>
              <input
                type="range"
                min={0}
                max={1.5}
                step={0.05}
                value={draft.temperature}
                onChange={(event) =>
                  update("temperature", Number(event.target.value))
                }
              />
            </label>

            <label className="rf-settings__field">
              <span>Max agent steps</span>
              <input
                type="number"
                min={5}
                max={200}
                value={draft.maxAgentSteps}
                onChange={(event) =>
                  update(
                    "maxAgentSteps",
                    Math.max(5, Math.min(200, Number(event.target.value) || 40)),
                  )
                }
              />
            </label>

            <label className="rf-settings__toggle">
              <input
                type="checkbox"
                checked={draft.shoppingSkillEnabled}
                onChange={(event) =>
                  update("shoppingSkillEnabled", event.target.checked)
                }
              />
              <span>Enable shopping skill</span>
            </label>
          </section>

          {error && (
            <p className="rf-settings__error" role="alert">
              {error}
            </p>
          )}
          {notice && (
            <p className="rf-settings__notice" role="status">
              {notice}
            </p>
          )}

          <footer className="rf-settings__actions">
            <button
              type="button"
              className="rf-settings__ghost"
              onClick={handleReset}
              disabled={busy}
            >
              Reset
            </button>
            <button
              type="button"
              className="rf-settings__secondary"
              onClick={() => void handleTest()}
              disabled={busy}
            >
              {action === "testing" ? "Testing…" : "Test connection"}
            </button>
            <button type="submit" className="rf-settings__primary" disabled={busy}>
              {action === "saving" ? "Saving…" : "Save"}
            </button>
          </footer>
        </form>
      </div>
    </div>
  );
}

export function toConfigureOptions(
  settings: AgentSettings,
): AgentConfigureOptions {
  return settingsToConfigurePayload(settings);
}
