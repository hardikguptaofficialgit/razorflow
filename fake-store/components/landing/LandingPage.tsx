import Image from "next/image";
import Link from "next/link";
import type { ReactNode } from "react";

import { StoreLogo } from "@/components/StoreLogo";
import { demoRoutes } from "@/lib/demo-routes";

const HERO_IMAGE =
  "https://framerusercontent.com/images/AgsQPUMyQ2EU1x0eRlaGQaW6M.jpg";

const PACKAGES = [
  {
    name: "@hardik21232323/razorflow-protocol",
    role: "Wire types",
    detail:
      "Shared schemas for observations, actions, and WebSocket messages.",
  },
  {
    name: "@hardik21232323/razorflow-browser",
    role: "Browser layer",
    detail: "BrowserEnvironment interface and DOM observation builders.",
  },
  {
    name: "@hardik21232323/razorflow-client",
    role: "Agent SDK",
    detail:
      "RazorFlow client, transport, and run lifecycle for any web app.",
  },
] as const;

const EXTENSION_FEATURES = [
  {
    title: "Chrome MV3 extension",
    detail:
      "Manifest V3 extension with popup UI, background service worker, and content-script overlay on live storefronts.",
  },
  {
    title: "Extension-first execution",
    detail:
      "The extension is the only component that clicks, types, and navigates real pages. The SDK and Python runtime propose actions.",
  },
  {
    title: "Agent backend bridge",
    detail:
      "Connects to the runtime over WebSocket (default ws://127.0.0.1:8765/ws) for planning, policy gates, pause/resume, and run lifecycle.",
  },
] as const;

const EXTENSION_STEPS = [
  "cd extension && npm install && npm run build",
  "Load extension/dist/ as an unpacked extension in chrome://extensions",
  "Start the agent backend and demo store, then launch a task from the popup or overlay",
] as const;

const STEPS = [
  {
    title: "Observe",
    body: "Capture a structured snapshot of the live page, elements, products, cart state.",
  },
  {
    title: "Plan",
    body: "The runtime LLM picks the next 1–3 actions from real DOM targets.",
  },
  {
    title: "Act & verify",
    body: "Your BrowserEnvironment executes clicks and types, then verifies progress.",
  },
] as const;

type NavLink =
  | { href: string; label: string; external?: false }
  | { href: string; label: string; external: true };

const NAV_LINKS: NavLink[] = [
  { href: "#extension", label: "Extension" },
  { href: "#sdk", label: "SDK" },
  { href: "#how-it-works", label: "How it works" },
  {
    href: "https://www.npmjs.com/~hardik21232323",
    label: "npm",
    external: true,
  },
];

function SectionLabel({ children }: { children: ReactNode }) {
  return (
    <p className="text-[11px] font-semibold uppercase tracking-[0.18em] text-[#3567e8]">
      {children}
    </p>
  );
}

function PrimaryButton({
  href,
  children,
  external,
}: {
  href: string;
  children: ReactNode;
  external?: boolean;
}) {
  const className =
    "inline-flex items-center justify-center rounded-lg bg-[#0b1020] px-5 py-2.5 text-[13px] font-semibold text-white transition-colors duration-150 hover:bg-[#171d30]";

  if (external) {
    return (
      <a href={href} target="_blank" rel="noreferrer" className={className}>
        {children}
      </a>
    );
  }

  return (
    <Link href={href} className={className}>
      {children}
    </Link>
  );
}

export function LandingPage() {
  return (
    <div className="rf-landing min-h-screen overflow-x-hidden bg-[#f7f8fc] text-[#0b1020]">
      {/* Header */}
      <header className="rf-landing-nav sticky top-0 z-50 border-b border-[#e6e9f0] bg-white/95 backdrop-blur-sm">
        <div className="mx-auto flex h-14 max-w-6xl items-center justify-between gap-4 px-4 sm:h-16 sm:px-6 lg:px-8">
          <Link
            href="/"
            className="inline-flex shrink-0 items-center gap-2.5"
            aria-label="RazorFlow home"
          >
            <StoreLogo size={32} priority />
            <span className="font-display text-[17px] font-bold tracking-[-0.03em] text-[#0b1020]">
              RazorFlow
            </span>
          </Link>

          <nav
            className="hidden items-center gap-6 text-[13px] font-medium text-[#5c6478] md:flex"
            aria-label="Primary"
          >
            {NAV_LINKS.map((link) =>
              link.external ? (
                <a
                  key={link.href}
                  href={link.href}
                  target="_blank"
                  rel="noreferrer"
                  className="transition-colors duration-150 hover:text-[#0b1020]"
                >
                  {link.label}
                </a>
              ) : (
                <a
                  key={link.href}
                  href={link.href}
                  className="transition-colors duration-150 hover:text-[#0b1020]"
                >
                  {link.label}
                </a>
              ),
            )}
          </nav>

          <PrimaryButton href={demoRoutes.home}>Try live demo</PrimaryButton>
        </div>
      </header>

      {/* Hero */}
      <section className="rf-landing-hero relative isolate min-h-[520px] overflow-hidden sm:min-h-[580px]">
        <Image
          src={HERO_IMAGE}
          alt=""
          fill
          priority
          sizes="100vw"
          className="rf-landing-hero__bg object-cover object-[center_35%]"
          aria-hidden
        />

        <div className="relative mx-auto flex min-h-[520px] max-w-6xl items-center px-4 py-14 sm:min-h-[580px] sm:px-6 sm:py-16 lg:px-8">
          <div className="max-w-2xl">
            <p className="text-[11px] font-semibold uppercase tracking-[0.18em] text-white/75">
              Agentic commerce SDK
            </p>

            <h1 className="mt-3 max-w-xl font-display text-[34px] font-semibold leading-[1.06] tracking-[-0.04em] text-white sm:text-[44px] lg:text-[52px] [text-shadow:0_2px_28px_rgba(0,0,0,0.45)]">
              Ship browser agents that browse, compare, and checkout on any site.
            </h1>

            <p className="mt-4 max-w-lg text-[15px] leading-relaxed text-white/88 sm:text-[16px] [text-shadow:0_1px_16px_rgba(0,0,0,0.4)]">
              RazorFlow is a TypeScript SDK plus Python runtime. Plug your app
              in with{" "}
              <code className="rounded border border-white/30 bg-black/25 px-1.5 py-0.5 font-mono text-[0.88em] text-white">
                BrowserEnvironment
              </code>
              , connect over WebSocket, and let the agent handle real DOM
              actions with verification and policy gates.
            </p>

            <div className="mt-6 flex flex-wrap items-center gap-2.5">
              <Link
                href={demoRoutes.home}
                className="inline-flex items-center justify-center rounded-lg bg-white px-5 py-2.5 text-[13px] font-semibold text-[#0b1020] transition-colors duration-150 hover:bg-white/92"
              >
                Open demo store
              </Link>
              <a
                href="#sdk"
                className="inline-flex items-center justify-center rounded-lg border border-white/45 bg-white/10 px-5 py-2.5 text-[13px] font-semibold text-white transition-colors duration-150 hover:bg-white/15"
              >
                Explore packages
              </a>
            </div>
          </div>
        </div>

        <div
          className="pointer-events-none absolute inset-x-0 bottom-0 h-14 bg-gradient-to-t from-[#f7f8fc] to-transparent"
          aria-hidden
        />
      </section>

      {/* Extension */}
      <section
        id="extension"
        className="border-b border-[#e6e9f0] bg-[#f7f8fc] py-12 sm:py-14"
      >
        <div className="mx-auto max-w-6xl px-4 sm:px-6 lg:px-8">
          <div className="grid gap-8 lg:grid-cols-[minmax(0,0.9fr)_minmax(0,1.1fr)] lg:items-start lg:gap-10">
            <div>
              <SectionLabel>Chrome extension</SectionLabel>
              <h2 className="mt-2 font-display text-[28px] font-semibold leading-tight tracking-[-0.035em] text-[#0b1020] sm:text-[32px]">
                The live-page executor for RazorFlow
              </h2>
              <p className="mt-3 max-w-md text-[15px] leading-relaxed text-[#5c6478]">
                RazorFlow ships as a Chrome Manifest V3 extension. It overlays
                the active tab, runs DOM actions, and talks to the Python agent
                backend while the npm SDK handles typed proposals and run
                lifecycle in your app.
              </p>

              <div className="mt-5 inline-flex items-center gap-2 rounded-full border border-[#dce3f0] bg-white px-3 py-1.5 text-[12px] font-medium text-[#394155]">
                <span className="inline-flex h-2 w-2 rounded-full bg-[#3567e8]" />
                Extension-first execution on any storefront
              </div>
            </div>

            <div className="grid gap-3 sm:grid-cols-3 lg:grid-cols-1 xl:grid-cols-3">
              {EXTENSION_FEATURES.map((feature) => (
                <article
                  key={feature.title}
                  className="rounded-xl border border-[#e2e6ee] bg-white p-4"
                >
                  <h3 className="text-[14px] font-semibold text-[#101827]">
                    {feature.title}
                  </h3>
                  <p className="mt-2 text-[13px] leading-6 text-[#5c6478]">
                    {feature.detail}
                  </p>
                </article>
              ))}
            </div>
          </div>

          <div className="mt-6 overflow-hidden rounded-xl border border-[#dce2ec] bg-white">
            <div className="border-b border-[#e8ecf2] px-4 py-3 sm:px-5">
              <p className="text-[12px] font-semibold uppercase tracking-[0.12em] text-[#7b8498]">
                Load the extension locally
              </p>
            </div>
            <ol className="divide-y divide-[#eef1f6]">
              {EXTENSION_STEPS.map((step, index) => (
                <li
                  key={step}
                  className="flex gap-3 px-4 py-3.5 text-[13px] leading-6 text-[#394155] sm:px-5"
                >
                  <span className="mt-0.5 flex h-5 w-5 shrink-0 items-center justify-center rounded-full bg-[#edf2ff] text-[11px] font-bold text-[#3567e8]">
                    {index + 1}
                  </span>
                  <code className="font-mono text-[12px] leading-6 text-[#111827] sm:text-[13px]">
                    {step}
                  </code>
                </li>
              ))}
            </ol>
          </div>
        </div>
      </section>

      {/* SDK */}
      <section
        id="sdk"
        className="border-b border-[#e6e9f0] bg-white py-12 sm:py-14"
      >
        <div className="mx-auto max-w-6xl px-4 sm:px-6 lg:px-8">
          <div className="max-w-2xl">
            <SectionLabel>The stack</SectionLabel>
            <h2 className="mt-2 font-display text-[28px] font-semibold leading-tight tracking-[-0.035em] text-[#0b1020] sm:text-[32px]">
              Three packages, one agent stack
            </h2>
            <p className="mt-3 max-w-xl text-[15px] leading-relaxed text-[#5c6478]">
              Published on npm under{" "}
              <span className="font-semibold text-[#20283a]">
                @hardik21232323
              </span>
              . Install the client in your app; the runtime stays server-side.
            </p>
          </div>

          <div className="mt-8 grid gap-3 md:grid-cols-3">
            {PACKAGES.map((pkg, index) => (
              <article
                key={pkg.name}
                className="rounded-xl border border-[#e2e6ee] bg-[#f8f9fc] p-5"
              >
                <div className="flex items-start justify-between gap-3">
                  <p className="text-[10px] font-bold uppercase tracking-[0.16em] text-[#8992a5]">
                    {pkg.role}
                  </p>
                  <span className="font-mono text-[10px] font-semibold tracking-[0.1em] text-[#c5ccd8]">
                    0{index + 1}
                  </span>
                </div>

                <h3 className="mt-2 break-words font-mono text-[12px] font-semibold leading-5 tracking-[-0.01em] text-[#111827] sm:text-[13px]">
                  {pkg.name}
                </h3>

                <p className="mt-3 text-[13px] leading-6 text-[#5c6478]">
                  {pkg.detail}
                </p>
              </article>
            ))}
          </div>

          <div className="mt-5 overflow-hidden rounded-xl border border-[#dce2ec] bg-[#0b1020]">
            <div className="flex items-center gap-2 border-b border-white/[0.08] px-4 py-3 sm:px-5">
              <span className="h-2 w-2 rounded-full bg-white/25" />
              <span className="h-2 w-2 rounded-full bg-white/25" />
              <span className="h-2 w-2 rounded-full bg-white/25" />
              <span className="ml-2 font-mono text-[11px] text-white/45">
                razorflow.ts
              </span>
            </div>

            <pre className="overflow-x-auto p-4 text-[12px] leading-6 text-white/80 sm:p-5 sm:text-[13px] sm:leading-7">
              <code>{`npm install @hardik21232323/razorflow-client @hardik21232323/razorflow-browser

import RazorFlow from "@hardik21232323/razorflow-client";
import { myEnvironment } from "./my-environment";

const rf = new RazorFlow({
  endpoint: "ws://127.0.0.1:8765/ws",
  environment: myEnvironment,
});

await rf.run({ task: "find wireless earbuds under ₹5000" });`}</code>
            </pre>
          </div>
        </div>
      </section>

      {/* How it works */}
      <section
        id="how-it-works"
        className="border-b border-[#e6e9f0] bg-[#f7f8fc] py-12 sm:py-14"
      >
        <div className="mx-auto max-w-6xl px-4 sm:px-6 lg:px-8">
          <div className="max-w-2xl">
            <SectionLabel>Runtime flow</SectionLabel>
            <h2 className="mt-2 font-display text-[28px] font-semibold leading-tight tracking-[-0.035em] text-[#0b1020] sm:text-[32px]">
              How it works
            </h2>
          </div>

          <div className="mt-8 grid gap-3 md:grid-cols-3">
            {STEPS.map((step, index) => (
              <article
                key={step.title}
                className="rounded-xl border border-[#e2e6ee] bg-white p-5"
              >
                <div className="flex h-8 w-8 items-center justify-center rounded-full border border-[#d9e3fb] bg-[#edf3ff] text-[11px] font-bold text-[#3567e8]">
                  {String(index + 1).padStart(2, "0")}
                </div>

                <h3 className="mt-4 font-display text-[18px] font-semibold tracking-[-0.02em] text-[#101827]">
                  {step.title}
                </h3>

                <p className="mt-2 text-[13px] leading-6 text-[#5c6478]">
                  {step.body}
                </p>
              </article>
            ))}
          </div>
        </div>
      </section>

      {/* CTA */}
      <section className="bg-[#0b1020] py-12 sm:py-14">
        <div className="mx-auto flex max-w-6xl flex-col gap-6 px-4 sm:px-6 lg:flex-row lg:items-center lg:justify-between lg:px-8">
          <div className="max-w-xl">
            <SectionLabel>Live environment</SectionLabel>
            <h2 className="mt-2 font-display text-[28px] font-semibold leading-tight tracking-[-0.035em] text-white sm:text-[32px]">
              See it on a real storefront
            </h2>
            <p className="mt-3 text-[15px] leading-relaxed text-white/65">
              The demo store at{" "}
              <code className="rounded border border-white/15 bg-white/10 px-1.5 py-0.5 font-mono text-[0.88em] text-white/90">
                /demo
              </code>{" "}
              embeds the full agent, search, add to cart, and checkout with
              conversational UI.
            </p>
          </div>

          <Link
            href={demoRoutes.home}
            className="inline-flex shrink-0 items-center justify-center rounded-lg bg-white px-5 py-2.5 text-[13px] font-semibold text-[#0b1020] transition-colors duration-150 hover:bg-[#f2f4f8]"
          >
            Launch demo store
          </Link>
        </div>
      </section>

      {/* Footer */}
      <footer className="border-t border-white/10 bg-[#080c18] py-6">
        <div className="mx-auto flex max-w-6xl flex-col gap-2 px-4 text-[12px] text-white/45 sm:flex-row sm:items-center sm:justify-between sm:px-6 lg:px-8">
          <span>RazorFlow, browser agent SDK for agentic commerce.</span>
          <span>Built for Razorpay AI Buildathon 2026</span>
        </div>
      </footer>
    </div>
  );
}
