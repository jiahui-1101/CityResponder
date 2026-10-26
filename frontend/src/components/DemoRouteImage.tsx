import { useState } from "react";
import type { RouteIndexItem } from "../api/routes";
import { selectDemoRouteVisualState } from "../routing/demoRouteImage";

export const DEMO_ROUTE_IMAGE_SOURCES = {
  main: "/assets/demo_routes/main-route.png",
  alternate: "/assets/demo_routes/alternate-route.png",
  no_safe_route: "/assets/demo_routes/no-safe-route.png",
} as const;

const STATE_LABELS = {
  main: "Main route demo image",
  alternate: "Alternate route demo image",
  no_safe_route: "No safe route demo image",
} as const;

export function DemoRouteImage({ route }: { route: RouteIndexItem }) {
  const state = selectDemoRouteVisualState(route);
  const src = DEMO_ROUTE_IMAGE_SOURCES[state];
  const [failedSource, setFailedSource] = useState<string | null>(null);
  const imageFailed = failedSource === src;

  return <div className="demo-route-image" data-demo-route-state={state}>
    {imageFailed
      ? <div className="demo-route-image-fallback" role="alert"><strong>Route image unavailable</strong><span>The selected demo image could not be loaded. Route details are still shown below.</span></div>
      : <img src={src} alt={STATE_LABELS[state]} onError={() => setFailedSource(src)} />}
    <p className="demo-route-image-caption">{STATE_LABELS[state]} · v{route.latest_version} · DEMO VISUAL</p>
  </div>;
}
