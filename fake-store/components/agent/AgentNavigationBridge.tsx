"use client";

import { useEffect } from "react";
import { useRouter } from "next/navigation";
import { registerAgentNavigate } from "@/lib/agent/navigation";

/** Wires Next.js router into the agent action executor for soft navigations. */
export function AgentNavigationBridge() {
  const router = useRouter();

  useEffect(() => {
    return registerAgentNavigate((path) => {
      router.push(path);
    });
  }, [router]);

  return null;
}
