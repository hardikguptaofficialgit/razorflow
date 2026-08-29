import fs from "node:fs";
import path from "node:path";

const TRANSCRIPT =
  "C:\\Users\\hardi\\.cursor\\projects\\c-Disk-E-Razorpay\\agent-transcripts\\eee3bb70-76f5-4e88-a78f-81bf5537b399\\eee3bb70-76f5-4e88-a78f-81bf5537b399.jsonl";
const ROOT = "C:\\Disk E\\Razorpay";

function normPath(p) {
  return p
    .replace(/\\/g, "/")
    .replace(/^[a-zA-Z]:\//, "")
    .replace(/^.*Razorpay\//i, "")
    .split("/")
    .join(path.sep);
}

const files = new Map();
const misses = [];

for (const line of fs.readFileSync(TRANSCRIPT, "utf8").split(/\r?\n/)) {
  if (!line.trim()) continue;
  let obj;
  try {
    obj = JSON.parse(line);
  } catch {
    continue;
  }
  const content = obj?.message?.content;
  if (!Array.isArray(content)) continue;
  for (const part of content) {
    if (part?.type !== "tool_use") continue;
    const name = part.name;
    const inp = part.input ?? {};
    const rawPath = inp.path ?? "";
    if (!/razorpay/i.test(rawPath)) continue;
    const rel = normPath(rawPath);
    if (name === "Write") {
      files.set(rel, inp.contents ?? "");
    } else if (name === "StrReplace") {
      const oldStr = inp.old_string ?? "";
      const newStr = inp.new_string ?? "";
      if (!files.has(rel)) {
        misses.push({ rel, kind: "no-base", old: oldStr.slice(0, 60) });
        continue;
      }
      const cur = files.get(rel);
      if (!cur.includes(oldStr)) {
        misses.push({ rel, kind: "patch-miss", old: oldStr.slice(0, 80) });
        continue;
      }
      files.set(rel, cur.replace(oldStr, newStr));
    }
  }
}

let written = 0;
for (const [rel, contents] of files) {
  const dest = path.join(ROOT, rel);
  fs.mkdirSync(path.dirname(dest), { recursive: true });
  fs.writeFileSync(dest, contents, "utf8");
  written++;
}

console.log(`Recovered ${written} files from transcript`);
console.log(`Patch misses: ${misses.length}`);
for (const m of misses.slice(0, 20)) {
  console.log(`  [${m.kind}] ${m.rel}: ${m.old}`);
}
