// Mimic the LocalSystem service child env (no per-user vars) and print the
// exact Playwright registry directory + chromium executable path it resolves to.
// This tells us where the running OmniRoute child is looking for Chromium.
for (const k of ["LOCALAPPDATA", "APPDATA", "USERPROFILE", "HOMEDRIVE", "HOMEPATH", "HOME", "PLAYWRIGHT_BROWSERS_PATH"]) {
  delete process.env[k];
}
const os = require("os");
const path = require("path");
console.log("cwd =", process.cwd());
console.log("os.homedir() =", os.homedir());

// Load the bundled playwright-core registry to get the real resolved path.
const pwCore = "C:\\Users\\Admin\\AppData\\Local\\hermes\\node\\node_modules\\omniroute\\node_modules\\playwright-core";
try {
  const { registry } = require(path.join(pwCore, "lib", "server", "registry"));
  const chromium = registry.findExecutable("chromium");
  console.log("chromium.executablePath =", chromium.executablePath());
  console.log("exists =", require("fs").existsSync(chromium.executablePath()));
} catch (e) {
  console.log("registry load failed:", e.message);
  // Fallback: replicate the defaultCacheDirectory logic.
  const dcd = process.env.LOCALAPPDATA || path.join(os.homedir(), "AppData", "Local");
  console.log("defaultCacheDirectory =", dcd);
  console.log("guessed ms-playwright =", path.join(dcd, "ms-playwright"));
}
