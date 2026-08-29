import fs from "node:fs";
import path from "node:path";

const TRANSCRIPT = process.argv[2];
const TARGET = process.argv[3]?.replace(/\\/g, "/").toLowerCase();
const ROOT = process.argv[4] || "C:\\Disk E\\Razorpay";

if (!TRANSCRIPT || !TARGET) {
  console.error("Usage: node extract-transcript-file.mjs <jsonl> <path-fragment> [root]");
  process.exit(1);
}

function norm(p) {
  return p.replace(/\\/g, "/").toLowerCase();
}

let content = null;
for (const line of fs.readFileSync(TRANSCRIPT, "utf8").split(/\r?\n/)) {
  if (!line.trim()) continue;
  let obj;
  try {
    obj = JSON.parse(line);
  } catch {
    continue;
  }
  for (const part of obj?.message?.content || []) {
    if (part?.type !== "tool_use" || part.name !== "Write") continue;
    const p = part.input?.path || "";
    if (!norm(p).includes(TARGET)) continue;
    content = part.input?.contents ?? "";
  }
}

if (!content) {
  console.error("No Write found for", TARGET);
  process.exit(1);
}

const rel = TARGET.includes("/") ? TARGET.split("razorpay/").pop() : TARGET;
const dest = path.join(ROOT, rel.replace(/\//g, path.sep));
fs.mkdirSync(path.dirname(dest), { recursive: true });
fs.writeFileSync(dest, content, "utf8");
console.log("Wrote", dest, `(${content.length} bytes)`);
