import { build, context } from "esbuild";
import { cpSync, mkdirSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const extRoot = join(dirname(fileURLToPath(import.meta.url)), "..");

const isWatch = process.argv.includes("--watch");

const entryPoints = [
  { input: "background/service-worker.ts", output: "background/service-worker" },
  { input: "content/content-script.ts", output: "content/content-script" },
  { input: "popup/popup.ts", output: "popup/popup" },
  { input: "offscreen/offscreen.ts", output: "offscreen/offscreen" },
];

const sharedOptions = {
  bundle: true,
  format: "esm",
  platform: "browser",
  target: "chrome120",
  sourcemap: true,
  logLevel: "info",
};

function copyStaticAssets() {
  mkdirSync(join(extRoot, "dist/popup"), { recursive: true });
  mkdirSync(join(extRoot, "dist/content"), { recursive: true });
  mkdirSync(join(extRoot, "dist/offscreen"), { recursive: true });
  mkdirSync(join(extRoot, "dist/assets/icons"), { recursive: true });
  cpSync(join(extRoot, "manifest.json"), join(extRoot, "dist/manifest.json"));
  cpSync(join(extRoot, "content/overlay.css"), join(extRoot, "dist/content/overlay.css"));
  cpSync(join(extRoot, "popup/popup.html"), join(extRoot, "dist/popup/popup.html"));
  cpSync(join(extRoot, "popup/popup.css"), join(extRoot, "dist/popup/popup.css"));
  cpSync(join(extRoot, "offscreen/offscreen.html"), join(extRoot, "dist/offscreen/offscreen.html"));
  cpSync(join(extRoot, "assets/logo.png"), join(extRoot, "dist/assets/logo.png"));
  cpSync(join(extRoot, "assets/dock-texture.png"), join(extRoot, "dist/assets/dock-texture.png"));
  cpSync(join(extRoot, "assets/icons/icon-16.png"), join(extRoot, "dist/assets/icons/icon-16.png"));
  cpSync(join(extRoot, "assets/icons/icon-48.png"), join(extRoot, "dist/assets/icons/icon-48.png"));
  cpSync(join(extRoot, "assets/icons/icon-128.png"), join(extRoot, "dist/assets/icons/icon-128.png"));
}

async function runBuild() {
  copyStaticAssets();

  if (isWatch) {
    const ctx = await context({
      ...sharedOptions,
      entryPoints: entryPoints.map(({ input, output }) => ({
        in: join(extRoot, input),
        out: output,
      })),
      outdir: join(extRoot, "dist"),
      outbase: extRoot,
    });

    await ctx.watch();
    console.log("Watching extension sources...");
    return;
  }

  await build({
    ...sharedOptions,
    entryPoints: entryPoints.map(({ input, output }) => ({
      in: join(extRoot, input),
      out: output,
    })),
    outdir: join(extRoot, "dist"),
    outbase: extRoot,
  });
}

await runBuild();
