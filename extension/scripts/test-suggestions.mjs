import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const root = join(dirname(fileURLToPath(import.meta.url)), "..");

function loadCatalog(absPath) {
  const source = readFileSync(absPath, "utf8");
  const tasks = [...source.matchAll(/task:\s*"([^"]+)"/g)].map((m) => m[1]);
  const ids = [...source.matchAll(/id:\s*"([^"]+)"/g)].map((m) => m[1]);
  const labels = [...source.matchAll(/label:\s*"([^"]+)"/g)].map((m) => m[1]);
  const categories = [
    ...source.matchAll(/category:\s*"([^"]+)"/g),
  ].map((m) => m[1]);
  return { tasks, ids, labels, categories };
}

const extension = loadCatalog(join(root, "shared/task-suggestions.ts"));
const fakeStore = loadCatalog(
  join(root, "..", "fake-store", "lib", "agent", "task-suggestions.ts"),
);

assert.deepEqual(
  extension.tasks,
  fakeStore.tasks,
  "extension and fake-store task strings must match",
);
assert.deepEqual(extension.ids, fakeStore.ids, "suggestion ids must match");
assert.equal(new Set(extension.ids).size, extension.ids.length, "no duplicate ids");

for (const required of ["search", "shopping", "compare", "cart", "checkout"]) {
  assert.ok(
    extension.categories.includes(required),
    `missing category: ${required}`,
  );
}

assert.ok(extension.tasks.length >= 5, "should expose multiple useful suggestions");
assert.ok(
  extension.labels.every((label) => label.length >= 8 && label.length <= 48),
  "labels should stay concise",
);

console.log(`suggestions-ui: ${extension.tasks.length} prompts OK`);
