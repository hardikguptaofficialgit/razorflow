"use client";

import {
  createContext,
  useCallback,
  useContext,
  useMemo,
  useState,
  type ReactNode,
} from "react";

export type AuthModalView = "login" | "signup";

interface AuthModalContextValue {
  isOpen: boolean;
  view: AuthModalView;
  nextPath: string | null;
  openAuth: (view?: AuthModalView, nextPath?: string | null) => void;
  closeAuth: () => void;
  setView: (view: AuthModalView) => void;
}

const AuthModalContext = createContext<AuthModalContextValue | null>(null);

export function AuthModalProvider({ children }: { children: ReactNode }) {
  const [isOpen, setIsOpen] = useState(false);
  const [view, setView] = useState<AuthModalView>("login");
  const [nextPath, setNextPath] = useState<string | null>(null);

  const openAuth = useCallback(
    (nextView: AuthModalView = "login", next: string | null = null) => {
      setView(nextView);
      setNextPath(next);
      setIsOpen(true);
    },
    [],
  );

  const closeAuth = useCallback(() => {
    setIsOpen(false);
    setNextPath(null);
  }, []);

  const value = useMemo(
    () => ({
      isOpen,
      view,
      nextPath,
      openAuth,
      closeAuth,
      setView,
    }),
    [isOpen, view, nextPath, openAuth, closeAuth],
  );

  return (
    <AuthModalContext.Provider value={value}>{children}</AuthModalContext.Provider>
  );
}

export function useAuthModal(): AuthModalContextValue {
  const ctx = useContext(AuthModalContext);
  if (!ctx) {
    throw new Error("useAuthModal must be used within AuthModalProvider");
  }
  return ctx;
}
