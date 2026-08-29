"use client";

import { useToast } from "@/lib/toast-context";

export function ToastViewport() {
  const { toasts, dismissToast } = useToast();

  if (toasts.length === 0) {
    return null;
  }

  return (
    <div
      className="rf-toast-viewport"
      role="region"
      aria-live="polite"
      aria-label="Notifications"
    >
      {toasts.map((toast) => (
        <div
          key={toast.id}
          className={`rf-toast rf-toast--${toast.tone}`}
          role="status"
        >
          <p className="rf-toast__message">{toast.message}</p>
          <button
            type="button"
            className="rf-toast__close"
            onClick={() => dismissToast(toast.id)}
            aria-label="Dismiss notification"
          >
            ×
          </button>
        </div>
      ))}
    </div>
  );
}
