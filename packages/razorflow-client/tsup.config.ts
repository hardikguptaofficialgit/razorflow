import { defineConfig } from "tsup";

export default defineConfig({
  entry: ["src/index.ts"],
  format: ["esm"],
  dts: true,
  clean: true,
  sourcemap: true,
  external: ["@hardik21232323/razorflow-protocol", "@hardik21232323/razorflow-browser"],
});
