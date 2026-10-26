import assert from "node:assert/strict";
import fs from "node:fs";
import ts from "typescript";

const sourceUrl = new URL("../src/routing/demoRouteImage.ts", import.meta.url);
const source = fs.readFileSync(sourceUrl, "utf8");
const compiled = ts.transpileModule(source, { compilerOptions: { target: ts.ScriptTarget.ES2022, module: ts.ModuleKind.ES2022 } }).outputText;
const { selectDemoRouteVisualState } = await import(`data:text/javascript;base64,${Buffer.from(compiled).toString("base64")}`);
const base = { status: "route_found", source_node_id: "N2", destination_node_id: "N5", no_safe_route: false, route_changed: true, previous_version: null, node_path: ["N2", "N4", "N5"], edge_path: ["PE04", "PE06"], reasons: [] };

assert.equal(selectDemoRouteVisualState(base), "main", "the first route version must remain main even though backend marks initial route_changed true");
assert.equal(selectDemoRouteVisualState({ ...base, node_path: ["N2", "N6", "N7"], edge_path: ["PE02", "PE07"], route_changed: false }), "alternate", "confirmed alternate path IDs select the alternate image");
assert.equal(selectDemoRouteVisualState({ ...base, destination_node_id: "N7", node_path: [], edge_path: [], route_changed: true }), "alternate", "a first-version alternate destination selects its image even without an edge path");
assert.equal(selectDemoRouteVisualState({ ...base, node_path: ["FIRE_STATION", "ALTERNATE", "BUILDING_A"], edge_path: ["ALTERNATE_ROUTE"] }), "alternate", "legacy alternate route labels select the alternate image without geometry mapping");
assert.equal(selectDemoRouteVisualState({ ...base, previous_version: 1, route_changed: true }), "alternate", "a changed later version selects the rerouted image");
assert.equal(selectDemoRouteVisualState({ ...base, no_safe_route: true }), "no_safe_route", "no_safe_route boolean takes precedence over path hints");
assert.equal(selectDemoRouteVisualState({ ...base, status: "ROUTE_NOT_FOUND", node_path: [], edge_path: [], route_changed: false }), "no_safe_route", "route_not_found status selects the no-safe image");
assert.equal(selectDemoRouteVisualState({ ...base, status: "invalid_configuration", node_path: [], edge_path: [], route_changed: false }), "no_safe_route", "unknown/error route status fails safely to no-safe image");

const expectedAssets = ["main-route.png", "alternate-route.png", "no-safe-route.png"];
for (const name of expectedAssets) {
  const path = new URL(`../public/assets/demo_routes/${name}`, import.meta.url);
  const bytes = fs.readFileSync(path);
  assert.equal(bytes.subarray(0, 8).toString("hex"), "89504e470d0a1a0a", `${name} must be a PNG`);
  assert.equal(bytes.readUInt32BE(16), 1920, `${name} must preserve 1920 pixel width`);
  assert.equal(bytes.readUInt32BE(20), 1080, `${name} must preserve 1080 pixel height`);
}

const component = fs.readFileSync(new URL("../src/components/DemoRouteImage.tsx", import.meta.url), "utf8");
assert.match(component, /onError=\{\(\) => setFailedSource\(src\)\}/, "image load errors must activate the fallback state");
assert.match(component, /role="alert"/, "image load fallback must be announced to assistive technology");
console.log("demo route image selection PASS: main, alternate, rerouted, no-safe, PNG assets, and missing-image fallback contract");
