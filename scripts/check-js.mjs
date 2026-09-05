import { spawnSync } from "node:child_process";
import { readdirSync, statSync } from "node:fs";
import { join } from "node:path";

const roots = ["prototype", "webmcp", "integration", "cloudflare/src", "tests-js", "scripts"];
const files = [];
function walk(path) {
  let entries;
  try { entries = readdirSync(path); } catch { return; }
  for (const entry of entries) {
    const full = join(path, entry);
    const stat = statSync(full);
    if (stat.isDirectory()) walk(full);
    else if (/\.(?:js|mjs)$/.test(entry) && !entry.endsWith(".min.js")) files.push(full);
  }
}
for (const root of roots) walk(root);
for (const file of files) {
  const result = spawnSync(process.execPath, ["--check", file], { stdio: "inherit" });
  if (result.status !== 0) process.exit(result.status ?? 1);
}
console.log(`Checked ${files.length} JavaScript files`);
