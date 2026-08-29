#!/usr/bin/env node
/**
 * Clean-project install test for published SDK packages.
 * Packs protocol → browser → client and installs them into an empty temp project.
 */

import assert from "node:assert/strict";
import { execSync } from "node:child_process";
import { mkdtempSync, mkdirSync, writeFileSync, rmSync, readdirSync } from "node:fs";
import { tmpdir } from "node:os";
import { dirname, join, resolve } from "node:path";
import { fileURLToPath, pathToFileURL } from "node:url";

const root = resolve(dirname(fileURLToPath(import.meta.url)), "..");

function runNpm(args, cwd = root) {
  execSync(`npm ${args.join(" ")}`, { cwd, stdio: "inherit", shell: true });
}
const packOrder = [
  "@hardik21232323/razorflow-protocol",
  "@hardik21232323/razorflow-browser",
  "@hardik21232323/razorflow-client",
];

function packWorkspace(name) {
  const before = new Set(readdirSync(packDir));
  execSync(`npm pack -w ${name} --pack-destination "${packDir}"`, {
    cwd: root,
    stdio: "pipe",
    shell: true,
  });
  const created = readdirSync(packDir).filter(
    (file) => file.endsWith(".tgz") && !before.has(file),
  );
  assert.equal(created.length, 1, `expected one tarball for ${name}`);
  return join(packDir, created[0]);
}

const packDir = mkdtempSync(join(tmpdir(), "razorflow-pack-"));
const installRoot = mkdtempSync(join(tmpdir(), "razorflow-clean-"));

try {
  runNpm(["run", "build:sdk"]);

  const tarballs = packOrder.map(packWorkspace);

  mkdirSync(installRoot, { recursive: true });
  writeFileSync(
    join(installRoot, "package.json"),
    JSON.stringify(
      {
        name: "razorflow-clean-install-fixture",
        private: true,
        type: "module",
        dependencies: Object.fromEntries(
          packOrder.map((name, index) => [name, `file:${tarballs[index]}`]),
        ),
      },
      null,
      2,
    ),
  );

  execSync("npm install --no-audit --no-fund", {
    cwd: installRoot,
    stdio: "inherit",
    shell: true,
  });

  const entry = join(installRoot, "node_modules", "@hardik21232323", "razorflow-client", "dist", "index.js");
  const { RazorFlow, RazorFlowError } = await import(pathToFileURL(entry).href);
  assert.equal(typeof RazorFlow, "function");
  assert.equal(typeof RazorFlowError, "function");

  console.log("SDK clean-install: OK");
  console.log(`  packed ${packOrder.join(" → ")}`);
  console.log(`  installed into ${installRoot}`);
} finally {
  rmSync(packDir, { recursive: true, force: true });
  rmSync(installRoot, { recursive: true, force: true });
}
