import fs from "node:fs";

const map = fs.readFileSync(new URL("../src/components/RouteMap.tsx", import.meta.url), "utf8");
const response = fs.readFileSync(new URL("../src/pages/FirefighterResponsePage.tsx", import.meta.url), "utf8");
const operator = fs.readFileSync(new URL("../src/pages/OperatorOverviewPage.tsx", import.meta.url), "utf8");
const simulation = fs.readFileSync(new URL("../src/pages/SimulationResultsPage.tsx", import.meta.url), "utf8");
const live = fs.readFileSync(new URL("../src/components/LiveVisionPanel.tsx", import.meta.url), "utf8");
const geometry = JSON.parse(fs.readFileSync(new URL("../src/data/routeGeometry.json", import.meta.url), "utf8"));
const image = new URL("../public/assets/city-model-phase-b1-final-review.jpg", import.meta.url);
const failures = [];
const requireText = (source, value, message) => { if (!source.includes(value)) failures.push(message); };

if (geometry.image_width !== 1920 || geometry.image_height !== 1080) failures.push("geometry must retain native camera dimensions");
for (const id of ["N2","N4","N5","N6","N7"]) if (!geometry.nodes[id]) failures.push(`missing documented node ${id}`);
for (const id of ["PE02","PE04","PE06","PE07"]) if (!geometry.edges[id]) failures.push(`missing documented edge ${id}`);
if (!fs.existsSync(image)) failures.push("real tabletop image asset is missing");
requireText(map, "preserveAspectRatio=\"xMidYMid meet\"", "responsive SVG must preserve aspect ratio");
requireText(map, "missing.length", "unknown geometry must fail visibly");
requireText(map, "selectedSequenceMismatch", "inconsistent backend route sequences must fail visibly");
requireText(map, "Unknown nodes:", "unknown backend graph nodes must fail visibly");
requireText(map, "No invalid path is drawn", "no-safe-route must clear invalid path");
requireText(map, "ROUTE IMAGE UNAVAILABLE", "tabletop image failure must be explicit");
requireText(map, "onError={() => setImageState(\"error\")}", "tabletop image load failure must be detected");
requireText(response, "current.node_path, edgeIds: current.edge_path", "Current Route must use persisted backend IDs");
requireText(response, "current-route-map-card", "Current Route image must be promoted to a primary card");
requireText(response, "Supporting node/edge sequence", "the strip must be described as supporting detail");
requireText(operator, "currentRoute.node_path, edgeIds: currentRoute.edge_path", "operator Current Route must use persisted backend IDs");
requireText(operator, "current-route-map-card", "operator dashboard must show the route image card");
requireText(simulation, "plan.road_states", "simulation road styling must use backend scenario state");
requireText(simulation, "Live AI Observation", "live and simulated views must remain separate");
requireText(live, "Mapped physical edges:", "shadow mode must expose mapping uncertainty");
if (failures.length) { console.error(failures.join("\n")); process.exit(1); }
console.log("route visualization and shadow-mode contract PASS");
