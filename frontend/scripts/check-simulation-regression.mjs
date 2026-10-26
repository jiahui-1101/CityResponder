import fs from "node:fs";

const page = fs.readFileSync(new URL("../src/pages/SimulationResultsPage.tsx", import.meta.url), "utf8");
const app = fs.readFileSync(new URL("../src/App.tsx", import.meta.url), "utf8");
const nav = fs.readFileSync(new URL("../src/navigation.ts", import.meta.url), "utf8");
const data = JSON.parse(fs.readFileSync(new URL("../src/data/phase3SimulationResults.json", import.meta.url), "utf8"));
const checks = [
  [data.simulation_marker === "SIMULATED", "report must be SIMULATED"],
  [data.summary.failed === 0 && data.summary.total === 11, "all 11 scenarios must pass"],
  [data.production_database_used === false, "production database must be unused"],
  [data.mqtt_transport_available === false, "MQTT transport must be unavailable"],
  [page.includes("read-only demonstration"), "page must explain its read-only design"],
  [page.includes("SIMULATED"), "page must visibly label simulation"],
  [app.includes('path="simulation"'), "simulation route must exist"],
  [nav.includes('path: "/simulation"'), "simulation navigation must exist"],
];
for (const [passed, message] of checks) if (!passed) throw new Error(message);
console.log("simulation regression checks passed");
