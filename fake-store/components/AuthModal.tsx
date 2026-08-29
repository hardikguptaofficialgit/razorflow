"use client";

import { FormEvent, useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { useAuthModal } from "@/lib/auth-modal-context";
import { createClient } from "@/lib/supabase/client";
import { isSupabaseConfigured } from "@/lib/supabase/config";

function AuthForm({
  view,
  nextPath,
  onSuccess,
  onSwitchView,
}: {
  view: "login" | "signup";
  nextPath: string | null;
  onSuccess: () => void;
  onSwitchView: (view: "login" | "signup") => void;
}) {
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [displayName, setDisplayName] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    setError(null);
  }, [view]);

  async function handleLogin(event: FormEvent) {
    event.preventDefault();
    setError(null);

    if (!isSupabaseConfigured()) {
      setError("Supabase is not configured. Add keys to .env.local.");
      return;
    }

    const supabase = createClient();
    if (!supabase) {
      setError("Could not create Supabase client.");
      return;
    }

    setLoading(true);
    const { error: signInError } = await supabase.auth.signInWithPassword({
      email: email.trim(),
      password,
    });
    setLoading(false);

    if (signInError) {
      const msg = signInError.message.toLowerCase();
      if (msg.includes("email not confirmed")) {
        setError("Email is not confirmed. Sign up again or use the confirmation link.");
      } else if (msg.includes("invalid login")) {
        setError("Wrong email or password.");
      } else {
        setError(signInError.message);
      }
      return;
    }

    onSuccess();
  }

  async function handleSignup(event: FormEvent) {
    event.preventDefault();
    setError(null);

    if (!isSupabaseConfigured()) {
      setError("Supabase is not configured. Add keys to .env.local.");
      return;
    }

    const supabase = createClient();
    if (!supabase) {
      setError("Could not create Supabase client.");
      return;
    }

    setLoading(true);
    try {
      const res = await fetch("/api/auth/signup", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          email: email.trim(),
          password,
          displayName: displayName.trim() || undefined,
        }),
      });
      const payload = (await res.json()) as { error?: string };
      if (!res.ok) {
        setError(payload.error || "Sign up failed.");
        return;
      }

      const { error: signInError } = await supabase.auth.signInWithPassword({
        email: email.trim(),
        password,
      });
      if (signInError) {
        setError(signInError.message);
        return;
      }

      onSuccess();
    } catch {
      setError("Could not reach the signup API.");
    } finally {
      setLoading(false);
    }
  }

  const isLogin = view === "login";

  return (
    <form
      onSubmit={isLogin ? handleLogin : handleSignup}
      className="rf-auth-form"
    >
      <h2 id="auth-modal-title" className="rf-auth-form__title">
        {isLogin ? "Sign in" : "Create account"}
      </h2>
      <p className="rf-auth-form__subtitle">
        {isLogin
          ? "Sign in to save your cart and complete checkout."
          : "Join RazorFlow Market to save your cart across devices."}
      </p>

      {!isSupabaseConfigured() ? (
        <p className="rf-auth-form__notice">
          Configure Supabase env vars to enable authentication.
        </p>
      ) : null}

      {!isLogin ? (
        <label className="rf-auth-form__label">
          Name
          <input
            type="text"
            name="displayName"
            value={displayName}
            onChange={(event) => setDisplayName(event.target.value)}
            autoComplete="name"
            className="rf-auth-form__input"
          />
        </label>
      ) : null}

      <label className="rf-auth-form__label">
        Email
        <input
          type="email"
          name="email"
          autoComplete="username"
          value={email}
          onChange={(event) => setEmail(event.target.value)}
          className="rf-auth-form__input"
          required
        />
      </label>

      <label className="rf-auth-form__label">
        Password
        <input
          type="password"
          name="password"
          autoComplete={isLogin ? "current-password" : "new-password"}
          value={password}
          onChange={(event) => setPassword(event.target.value)}
          minLength={isLogin ? undefined : 6}
          className="rf-auth-form__input"
          required
        />
      </label>

      {error ? <p className="rf-auth-form__error">{error}</p> : null}

      <button
        type="submit"
        disabled={loading || !isSupabaseConfigured()}
        className="rf-btn-gloss rf-btn-gloss--block !py-3 disabled:opacity-60"
      >
        {loading
          ? isLogin
            ? "Signing in…"
            : "Creating account…"
          : isLogin
            ? "Sign in"
            : "Create account"}
      </button>

      <p className="rf-auth-form__switch">
        {isLogin ? "New here?" : "Already have an account?"}{" "}
        <button
          type="button"
          className="rf-auth-form__link"
          onClick={() => onSwitchView(isLogin ? "signup" : "login")}
        >
          {isLogin ? "Create an account" : "Sign in"}
        </button>
      </p>

      {nextPath ? (
        <p className="rf-auth-form__hint">
          You will return to{" "}
          <span className="font-medium text-[var(--rf-ink)]">{nextPath}</span>{" "}
          after signing in.
        </p>
      ) : null}
    </form>
  );
}

export function AuthModal() {
  const router = useRouter();
  const { isOpen, view, nextPath, closeAuth, setView } = useAuthModal();

  useEffect(() => {
    if (!isOpen) {
      return;
    }

    function onKeyDown(event: KeyboardEvent) {
      if (event.key === "Escape") {
        closeAuth();
      }
    }

    document.body.style.overflow = "hidden";
    window.addEventListener("keydown", onKeyDown);
    return () => {
      document.body.style.overflow = "";
      window.removeEventListener("keydown", onKeyDown);
    };
  }, [isOpen, closeAuth]);

  if (!isOpen) {
    return null;
  }

  function handleSuccess() {
    closeAuth();
    if (nextPath && nextPath.startsWith("/")) {
      router.push(nextPath);
    }
    router.refresh();
  }

  return (
    <div className="rf-modal-root" role="presentation">
      <button
        type="button"
        className="rf-modal-backdrop"
        aria-label="Close dialog"
        onClick={closeAuth}
      />
      <div
        className="rf-modal-panel"
        role="dialog"
        aria-modal="true"
        aria-labelledby="auth-modal-title"
        data-rf-auth-modal="true"
        data-rf-auth-next={nextPath ?? ""}
      >
        <button
          type="button"
          className="rf-modal-close"
          onClick={closeAuth}
          aria-label="Close"
        >
          ×
        </button>
        <AuthForm
          view={view}
          nextPath={nextPath}
          onSuccess={handleSuccess}
          onSwitchView={setView}
        />
      </div>
    </div>
  );
}
