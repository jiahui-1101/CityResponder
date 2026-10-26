import assert from "node:assert/strict";
import fs from "node:fs";
import ts from "typescript";

const geometry = JSON.parse(fs.readFileSync(new URL("../src/data/routeGeometry.json", import.meta.url), "utf8"));
const source = fs.readFileSync(new URL("../src/routing/routeGeometry.ts", import.meta.url), "utf8");
const compiled = ts.transpileModule(source, { compilerOptions: { target: ts.ScriptTarget.ES2022, module: ts.ModuleKind.ES2022 } }).outputText;
const { resolveRouteGeometry } = await import(`data:text/javascript;base64,${Buffer.from(compiled).toString("base64")}`);

const routeA = resolveRouteGeometry({ nodeIds: ["N2", "N4", "N5"], edgeIds: ["PE04", "PE06"] }, geometry);
assert.equal(routeA.ok, true, "the confirmed N2→N4→N5 route resolves");
assert.deepEqual(routeA.points, [geometry.nodes.N2.position, geometry.nodes.N4.position, geometry.nodes.N5.position], "route A points preserve edge order and junction continuity");

const reverseA = resolveRouteGeometry({ nodeIds: ["N5", "N4", "N2"], edgeIds: ["PE06", "PE04"] }, geometry);
assert.equal(reverseA.ok, true, "bidirectional edges resolve when traversed in reverse");
assert.deepEqual(reverseA.points, [geometry.nodes.N5.position, geometry.nodes.N4.position, geometry.nodes.N2.position], "reverse traversal reverses each edge geometry");

const routeB = resolveRouteGeometry({ nodeIds: ["N2", "N6", "N7"], edgeIds: ["PE02", "PE07"] }, geometry);
assert.equal(routeB.ok, true, "the confirmed gate-dependent N2→N6→N7 route resolves for drawing");
assert.equal(routeB.points.length, 4, "curved/multipart PE07 geometry is retained");
assert.deepEqual(routeB.points.at(-1), geometry.nodes.N7.position, "route B terminates at its backend destination node");

const v1 = resolveRouteGeometry({ nodeIds: ["N2", "N4", "N5"], edgeIds: ["PE04", "PE06"] }, geometry);
const v2 = resolveRouteGeometry({ nodeIds: ["N2", "N6", "N7"], edgeIds: ["PE02", "PE07"] }, geometry);
assert.equal(v1.ok && v2.ok && v1.points.at(-1).x !== v2.points.at(-1).x, true, "a newer route version resolves independently instead of reusing stale geometry");

const legacy = resolveRouteGeometry({ nodeIds: ["FIRE_STATION", "ALTERNATE", "BUILDING_A"], edgeIds: ["ALTERNATE_ROUTE"] }, geometry);
assert.equal(legacy.ok, false, "unmapped legacy persisted IDs remain unavailable");
assert.match(legacy.reason, /inconsistent/);
assert.match(legacy.reason, /FIRE_STATION.*ALTERNATE.*BUILDING_A/);
assert.match(legacy.reason, /ALTERNATE_ROUTE/);

const disconnected = resolveRouteGeometry({ nodeIds: ["N2", "N4", "N5"], edgeIds: ["PE04", "PE07"] }, geometry);
assert.equal(disconnected.ok, false, "an existing edge with the wrong endpoints is rejected");
assert.match(disconnected.reason, /does not connect N4/);

const badEndpointGeometry = structuredClone(geometry);
badEndpointGeometry.edges.PE04.points[1] = { x: 200, y: 200 };
const badEndpoint = resolveRouteGeometry({ nodeIds: ["N2", "N4"], edgeIds: ["PE04"] }, badEndpointGeometry);
assert.equal(badEndpoint.ok, false, "edge coordinates that do not end on their declared node are rejected");
assert.match(badEndpoint.reason, /do not align/);

const missingEdge = resolveRouteGeometry({ nodeIds: ["N2", "N4"], edgeIds: ["E1"] }, geometry);
assert.equal(missingEdge.ok, false, "unmapped edge IDs cannot be drawn");
assert.match(missingEdge.reason, /E1/);

assert.equal(fs.existsSync(new URL("../public/assets/city-model-phase-b1-final-review.jpg", import.meta.url)), true, "the reviewed tabletop background asset exists");
console.log("route geometry validation PASS: canonical forward/reverse, multi-point, reroute, legacy, disconnected, endpoint, unknown-edge, and image-asset cases");
