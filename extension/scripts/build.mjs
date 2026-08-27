import { build, context } from "esbuild";
import { cpSync, mkdirSync } from "node:fs";

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
  mkdirSync("dist/popup", { recursive: true });
  mkdirSync("dist/content", { recursive: true });
  mkdirSync("dist/offscreen", { recursive: true });
  mkdirSync("dist/assets/icons", { recursive: true });
  cpSync("manifest.json", "dist/manifest.json");
  cpSync("content/overlay.css", "dist/content/overlay.css");
  cpSync("popup/popup.html", "dist/popup/popup.html");
  cpSync("popup/popup.css", "dist/popup/popup.css");
  cpSync("offscreen/offscreen.html", "dist/offscreen/offscreen.html");
  cpSync("assets/logo.png", "dist/assets/logo.png");
  cpSync("assets/dock-texture.png", "dist/assets/dock-texture.png");
  cpSync("assets/icons/icon-16.png", "dist/assets/icons/icon-16.png");
  cpSync("assets/icons/icon-48.png", "dist/assets/icons/icon-48.png");
  cpSync("assets/icons/icon-128.png", "dist/assets/icons/icon-128.png");
}

async function runBuild() {
  copyStaticAssets();

  if (isWatch) {
    const ctx = await context({
      ...sharedOptions,
      entryPoints: entryPoints.map(({ input, output }) => ({
        in: input,
        out: output,
      })),
      outdir: "dist",
      outbase: ".",
    });

    await ctx.watch();
    console.log("Watching extension sources...");
    return;
  }

  await build({
    ...sharedOptions,
    entryPoints: entryPoints.map(({ input, output }) => ({
      in: input,
      out: output,
    })),
    outdir: "dist",
    outbase: ".",
  });
}

await runBuild();
