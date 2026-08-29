import fs from "node:fs";
import path from "node:path";

const root = path.resolve("fake-store");
const imports = new Set();

function walk(dir) {
  for (const entry of fs.readdirSync(dir, { withFileTypes: true })) {
    if (entry.name.startsWith(".") || entry.name === "node_modules") continue;
    const full = path.join(dir, entry.name);
    if (entry.isDirectory()) walk(full);
    else if (/\.(tsx?|jsx?)$/.test(entry.name)) {
      const text = fs.readFileSync(full, "utf8");
      for (const match of text.matchAll(/from ["']@\/([^"']+)["']/g)) {
        imports.add(match[1]);
      }
    }
  }
}

walk(root);

const missing = [];
for (const imp of [...imports].sort()) {
  const candidates = [
    path.join(root, imp + ".ts"),
    path.join(root, imp + ".tsx"),
    path.join(root, imp, "index.ts"),
    path.join(root, imp, "index.tsx"),
  ];
  if (!candidates.some((c) => fs.existsSync(c))) {
    missing.push(imp);
  }
}

console.log("Missing imports:", missing.length);
for (const m of missing) console.log(" ", m);
