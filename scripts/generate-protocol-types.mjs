#!/usr/bin/env node
/** Sync @razorflow/protocol types header from shared/protocol/v2.schema.json (manual types for now). */
import { readFileSync, writeFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const root = join(dirname(fileURLToPath(import.meta.url)), "..");
const schemaPath = join(root, "shared", "protocol", "v2.schema.json");
const schema = JSON.parse(readFileSync(schemaPath, "utf8"));
const out = join(root, "packages", "razorflow-protocol", "src", "schema.json");
writeFileSync(out, JSON.stringify(schema, null, 2));
console.log("Wrote", out);
