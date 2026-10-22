import { readFileSync } from "node:fs";
import { resolve } from "node:path";

const root = resolve(import.meta.dirname, "..");
const overview = readFileSync(resolve(root, "src/hooks/useOperatorOverview.ts"), "utf8");
const incidents = readFileSync(resolve(root, "src/hooks/useIncidents.ts"), "utf8");
const risk = readFileSync(resolve(root, "src/hooks/useAreaRisk.ts"), "utf8");
const history = readFileSync(resolve(root, "src/hooks/useHistoryAudit.ts"), "utf8");
const calibration = readFileSync(resolve(root, "src/hooks/useCalibrationGovernance.ts"), "utf8");
const response = readFileSync(resolve(root, "src/hooks/useResponseView.ts"), "utf8");

const failures = [];
if (!overview.includes("loading: current[key].data === null")) failures.push("overview background refresh must preserve rendered sections");
if (!overview.includes("data: current[key].data")) failures.push("overview refresh failures must retain last known data");
if (!overview.includes("sectionVersions.current[key] !== version")) failures.push("overview must ignore stale section responses");
for (const [name, source] of Object.entries({ incidents, risk, history, calibration, response })) {
  if (/refresh[\s\S]{0,160}setLoading\(true\)/.test(source)) failures.push(`${name} refresh must not replace existing content with a loading screen`);
}
if (failures.length) {
  console.error(failures.join("\n"));
  process.exit(1);
}
console.log("Background-refresh regression contract PASS");
