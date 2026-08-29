import fs from "node:fs";
import path from "node:path";

const ROOT = "C:\\Disk E\\Razorpay";
const issues = [];

function walk(dir) {
  for (const entry of fs.readdirSync(dir, { withFileTypes: true })) {
    if (["node_modules", ".git", ".next", "dist", "__pycache__"].includes(entry.name)) {
      continue;
    }
    const full = path.join(dir, entry.name);
    if (entry.isDirectory()) {
      walk(full);
      continue;
    }
    if (!entry.name.endsWith(".py")) continue;
    const text = fs.readFileSync(full, "utf8");
    const rel = path.relative(ROOT, full);
    if (/\)"""[\s\S]*from __future__/.test(text)) {
      issues.push({ rel, kind: "merged-import-docstring" });
    }
    if (/from __future__/.test(text) && !text.trimStart().startsWith('"""') && !text.trimStart().startsWith("#") && !text.trimStart().startsWith("from __future__")) {
      const beforeFuture = text.split("from __future__")[0];
      if (beforeFuture.trim().length > 0 && !beforeFuture.trimStart().startsWith('"""')) {
        issues.push({ rel, kind: "imports-before-future" });
      }
    }
    try {
      // crude syntax: unmatched triple quotes
      const triple = (text.match(/"""/g) || []).length;
      if (triple % 2 !== 0) {
        issues.push({ rel, kind: "unbalanced-triple-quotes" });
      }
    } catch {
      /* ignore */
    }
  }
}

walk(ROOT);
console.log(`Found ${issues.length} potential Python issues:`);
for (const i of issues) {
  console.log(`  [${i.kind}] ${i.rel}`);
}
