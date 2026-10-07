const { spawn } = require("node:child_process");
const path = require("node:path");
const fs = require("node:fs");
const root = path.resolve(__dirname, "../..");
const localPython = path.join(root, ".venv", process.platform === "win32" ? "Scripts/python.exe" : "bin/python");
const python = fs.existsSync(localPython) ? localPython : "python";
let calculator, child;
let stopping = false;
function stop() { stopping = true; child?.kill(); calculator?.kill(); }
process.on("SIGINT", stop);
process.on("SIGTERM", stop);
async function ready() {
  try { const r = await fetch("http://localhost:8001/health", { signal: AbortSignal.timeout(1000) }); return (await r.json()).mode === "personal-preview"; }
  catch { return false; }
}
async function main() {
  if (!await ready()) {
    calculator = spawn(python, ["-m", "uvicorn", "api.preview:app", "--host", "127.0.0.1", "--port", "8001", "--no-access-log"],
      { cwd: root, stdio: "inherit", windowsHide: true });
    calculator.on("error", (e) => { console.error(e.message); stop(); process.exitCode = 1; });
    calculator.on("exit", (code) => { if (!stopping) { stop(); process.exitCode = code || 1; } });
    for (let i = 0; i < 40 && !stopping && !await ready(); i++) await new Promise((r) => setTimeout(r, 250));
    if (stopping || !await ready()) throw new Error("Personal preview calculator could not start. Install requirements.txt in .venv first.");
  }
  child = spawn(process.execPath, [require.resolve("expo/bin/cli"), "start", "--web", ...process.argv.slice(2)], {
    cwd: path.resolve(__dirname, ".."), stdio: "inherit", windowsHide: true,
    env: { ...process.env, EXPO_PUBLIC_DEMO: "1", EXPO_PUBLIC_DEV_LOGIN: "1", EXPO_OFFLINE: "1", EXPO_PUBLIC_PREVIEW_API_URL: "http://localhost:8001" },
  });
  child.on("error", (e) => { console.error(e.message); stop(); process.exitCode = 1; });
  child.on("exit", (code) => { stop(); process.exitCode = code ?? 1; });
}
main().catch((e) => { console.error(e.message); stop(); process.exitCode = 1; });
