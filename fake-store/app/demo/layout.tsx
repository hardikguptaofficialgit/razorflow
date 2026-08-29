import type { Metadata } from "next";
import { AgentNavigationBridge } from "@/components/agent/AgentNavigationBridge";
import { RazorflowAgent } from "@/components/agent/RazorflowAgent";
import { StoreHeader } from "@/components/StoreHeader";
import "../agent-overlay.css";

export const metadata: Metadata = {
  title: "Demo Store",
  description: "Live RazorFlow agent demo — search, compare, and checkout.",
};

export default function DemoStoreLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <div className="rf-store-shell flex min-h-screen flex-col">
      <AgentNavigationBridge />
      <StoreHeader />
      <div className="flex-1">{children}</div>
      <RazorflowAgent />
    </div>
  );
}
