import type { Metadata } from "next";
import { LandingPage } from "@/components/landing/LandingPage";

export const metadata: Metadata = {
  title: "RazorFlow — Browser Agent SDK",
  description:
    "TypeScript SDK and Python runtime for autonomous browser agents that shop, compare, and checkout on any website.",
};

export default function HomePage() {
  return <LandingPage />;
}
