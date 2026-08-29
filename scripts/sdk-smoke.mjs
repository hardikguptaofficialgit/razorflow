#!/usr/bin/env node
/** Verify SDK packages build and export expected symbols. */
import { readFileSync, existsSync } from "node:fs";
import { join, dirname } from "node:path";
import { fileURLToPath, pathToFileURL } from "node:url";

const root = join(dirname(fileURLToPath(import.meta.url)), "..");

const required = [
  "packages/razorflow-protocol/dist/index.js",
  "packages/razorflow-protocol/dist/index.d.ts",
  "packages/razorflow-browser/dist/index.js",
  "packages/razorflow-client/dist/index.js",
];

for (const rel of required) {
  const path = join(root, rel);
  if (!existsSync(path)) {
    console.error("Missing build artifact:", rel);
    process.exit(1);
  }
}

const clientJs = readFileSync(
  join(root, "packages/razorflow-client/dist/index.js"),
  "utf8",
);
if (!clientJs.includes("RazorFlow")) {
  console.error("RazorFlow export not found in client bundle");
  process.exit(1);
}

const {
  RazorFlow,
  WebSocketTransport,
  AgentRun,
  RazorFlowError,
  DomBrowserEnvironment,
  sanitizePageContextWire,
} = await import(
  pathToFileURL(join(root, "packages/razorflow-client/dist/index.js")).href
);

if (typeof RazorFlow !== "function") {
  console.error("RazorFlow export missing");
  process.exit(1);
}
if (typeof WebSocketTransport !== "function") {
  console.error("WebSocketTransport export missing");
  process.exit(1);
}
if (typeof AgentRun !== "function") {
  console.error("AgentRun export missing");
  process.exit(1);
}
if (typeof RazorFlowError !== "function") {
  console.error("RazorFlowError export missing");
  process.exit(1);
}
if (typeof DomBrowserEnvironment !== "function") {
  console.error("DomBrowserEnvironment export missing");
  process.exit(1);
}
if (typeof AgentRun.prototype.untilComplete !== "function") {
  console.error("AgentRun.untilComplete missing");
  process.exit(1);
}

const sanitized = sanitizePageContextWire({
  title: "Example",
  url: "https://example.com",
  elements: [
    {
      index: 1,
      role: "link",
      tag: "a",
      text: null,
      placeholder: null,
      ariaLabel: null,
    },
  ],
});
if (!sanitized.elements[0].text === "") {
  // text coerced to empty string
}
if (sanitized.elements[0].text !== "") {
  console.error("sanitizePageContextWire did not coerce null text");
  process.exit(1);
}

console.log("SDK smoke: OK");
console.log("  RazorFlow, WebSocketTransport, AgentRun, RazorFlowError exported");
console.log("  DomBrowserEnvironment + untilComplete available");
console.log("  dist/ artifacts present for protocol, browser, client");
