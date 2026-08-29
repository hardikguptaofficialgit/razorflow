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
    if (!open) return;

    setDraft(loadAgentSettings());
    setShowKey(false);
    setAction("idle");
    setError(null);
    setNotice(null);

    function onKeyDown(event: KeyboardEvent) {
      if (event.key === "Escape") {
        onClose();
      }
    }

    const previousOverflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    window.addEventListener("keydown", onKeyDown);

    return () => {
      document.body.style.overflow = previousOverflow;
      window.removeEventListener("keydown", onKeyDown);
    };
  }, [open, onClose]);

  const providerMeta = useMemo(
    () => PROVIDER_OPTIONS.find(({ id }) => id === draft.provider),
    [draft.provider],
  );

  if (!open) return null;

  const clearMessages = () => {
    setError(null);
    setNotice(null);
  };

  function update<K extends keyof AgentSettings>(
    key: K,
    value: AgentSettings[K],
  ) {
    setDraft((prev) => ({ ...prev, [key]: value }));
    clearMessages();
  }

  function handleProviderChange(provider: PlannerProvider) {
    const models =
      PROVIDER_OPTIONS.find(({ id }) => id === provider)?.models ?? [];

    setDraft((prev) => ({
      ...prev,
      provider,
      model: models.includes(prev.model)
        ? prev.model
        : models[0] ?? prev.model,
    }));

    clearMessages();
  }

  async function handleSave(event: FormEvent) {
    event.preventDefault();
    setAction("saving");
    clearMessages();

    try {
      if (draft.useByok && !draft.apiKey.trim()) {
        throw new Error("API key is required when BYOK is enabled.");
      }

      if (draft.useByok && !draft.model.trim()) {
        throw new Error("Model is required when BYOK is enabled.");
      }

      saveAgentSettings(draft);
      await onApply(draft);
      setNotice("Settings saved successfully.");
    } catch (err) {
      setError(
        err instanceof Error ? err.message : "Could not save settings.",
      );
    } finally {
      setAction("idle");
    }
  }

  async function handleTest() {
    setAction("testing");
    clearMessages();

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
      setError(
        err instanceof Error ? err.message : "Connection test failed.",
      );
    } finally {
      setAction("idle");
    }
  }

  function handleReset() {
    setDraft(resetAgentSettings());
    setShowKey(false);
    setError(null);
    setNotice("Reset to defaults. Save to apply.");
  }

  const busy = action !== "idle";

  return (
    <div
      className="rf-settings"
      role="presentation"
      onClick={onClose}
    >
      <div
        className="rf-settings__dialog"
        role="dialog"
        aria-modal="true"
        aria-labelledby="rf-settings-title"
        onClick={(event) => event.stopPropagation()}
      >
        <header className="rf-settings__header">
          <div className="rf-settings__title-wrap">
            <span className="rf-settings__eyebrow">AGENT</span>
            <h2 id="rf-settings-title">Settings</h2>
            <p className="rf-settings__subtitle">
              Configure your model and agent behavior.
            </p>
          </div>

          <button
            type="button"
            className="rf-settings__close"
            aria-label="Close settings"
            onClick={onClose}
          >
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" aria-hidden>
              <path
                d="M7 7l10 10M17 7 7 17"
                stroke="currentColor"
                strokeWidth="2"
                strokeLinecap="round"
              />
            </svg>
          </button>
        </header>

        <div
          className={`rf-settings__status ${
            connected
              ? "rf-settings__status--connected"
              : "rf-settings__status--offline"
          }`}
        >
          <span className="rf-settings__status-dot" aria-hidden />

          <div className="rf-settings__status-content">
            <strong>
              {connected ? "Connected to backend" : "Backend offline"}
            </strong>

            <span>
              {configStatus?.message ||
                (configStatus?.mode === "byok"
                  ? `Using BYOK · ${
                      configStatus.provider ?? draft.provider
                    }`
                  : "Using server default LLM")}
            </span>
          </div>
        </div>

        <form className="rf-settings__form" onSubmit={handleSave}>
          <section className="rf-settings__section">
            <div className="rf-settings__section-heading">
              <div>
                <h3>LLM provider</h3>
                <p>Select the model provider used by the agent.</p>
              </div>
            </div>

            <label className="rf-settings__field">
              <span>Provider</span>

              <select
                value={draft.provider}
                onChange={(event) =>
                  handleProviderChange(
                    event.target.value as PlannerProvider,
                  )
                }
                disabled={busy}
              >
                {PROVIDER_OPTIONS.map((option) => (
                  <option key={option.id} value={option.id}>
                    {option.label}
                  </option>
                ))}
              </select>
            </label>

            <label className="rf-settings__toggle">
              <span className="rf-settings__toggle-copy">
                <strong>Use my API key</strong>
                <small>Bring your own provider credentials.</small>
              </span>

              <input
                type="checkbox"
                checked={draft.useByok}
                onChange={(event) =>
                  update("useByok", event.target.checked)
                }
                disabled={busy}
              />
            </label>

            {draft.useByok && (
              <div className="rf-settings__byok">
                <label className="rf-settings__field">
                  <span>API key</span>

                  <div className="rf-settings__secret">
                    <input
                      type={showKey ? "text" : "password"}
                      value={draft.apiKey}
                      onChange={(event) =>
                        update("apiKey", event.target.value)
                      }
                      placeholder="Enter API key"
                      autoComplete="off"
                      spellCheck={false}
                      disabled={busy}
                    />

                    <button
                      type="button"
                      className="rf-settings__inline-action"
                      onClick={() => setShowKey((value) => !value)}
                      disabled={busy}
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
                    onChange={(event) =>
                      update("model", event.target.value)
                    }
                    placeholder={
                      providerMeta?.models[0] ?? "Enter model ID"
                    }
                    disabled={busy}
                  />

                  <datalist id="rf-settings-models">
                    {providerMeta?.models.map((model) => (
                      <option key={model} value={model} />
                    ))}
                  </datalist>
                </label>
              </div>
            )}
          </section>

          <section className="rf-settings__section">
            <div className="rf-settings__section-heading">
              <div>
                <h3>Agent behavior</h3>
                <p>Control creativity and execution limits.</p>
              </div>
            </div>

            <label className="rf-settings__field">
              <div className="rf-settings__range-header">
                <span>Temperature</span>
                <output>{draft.temperature.toFixed(2)}</output>
              </div>

              <input
                className="rf-settings__range"
                type="range"
                min={0}
                max={1.5}
                step={0.05}
                value={draft.temperature}
                onChange={(event) =>
                  update("temperature", Number(event.target.value))
                }
                disabled={busy}
              />

              <div className="rf-settings__range-labels">
                <span>Precise</span>
                <span>Creative</span>
              </div>
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
                    Math.max(
                      5,
                      Math.min(
                        200,
                        Number(event.target.value) || 40,
                      ),
                    ),
                  )
                }
                disabled={busy}
              />
            </label>

            <label className="rf-settings__toggle">
              <span className="rf-settings__toggle-copy">
                <strong>Shopping skill</strong>
                <small>Allow shopping workflows and actions.</small>
              </span>

              <input
                type="checkbox"
                checked={draft.shoppingSkillEnabled}
                onChange={(event) =>
                  update(
                    "shoppingSkillEnabled",
                    event.target.checked,
                  )
                }
                disabled={busy}
              />
            </label>
          </section>

          {error && (
            <div
              className="rf-settings__message rf-settings__message--error"
              role="alert"
            >
              <strong>Error</strong>
              <span>{error}</span>
            </div>
          )}

          {notice && (
            <div
              className="rf-settings__message rf-settings__message--success"
              role="status"
            >
              <strong>Done</strong>
              <span>{notice}</span>
            </div>
          )}

          <footer className="rf-settings__actions">
            <button
              type="button"
              className="rf-settings__reset"
              onClick={handleReset}
              disabled={busy}
            >
              Reset
            </button>

            <div className="rf-settings__actions-right">
              <button
                type="button"
                className="rf-settings__secondary"
                onClick={() => void handleTest()}
                disabled={busy}
              >
                {action === "testing"
                  ? "Testing…"
                  : "Test connection"}
              </button>

              <button
                type="submit"
                className="rf-settings__primary"
                disabled={busy}
              >
                {action === "saving" ? "Saving…" : "Save changes"}
              </button>
            </div>
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