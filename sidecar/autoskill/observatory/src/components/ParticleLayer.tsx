import { useEffect, useRef } from "react";
import { Application, Graphics } from "pixi.js";
import type { PipelineEdge } from "../types";

type Props = {
  edges: PipelineEdge[];
  reducedMotion: boolean;
};

export function ParticleLayer({ edges, reducedMotion }: Props) {
  const hostRef = useRef<HTMLDivElement | null>(null);
  const edgesRef = useRef(edges);

  useEffect(() => {
    edgesRef.current = edges;
  }, [edges]);

  useEffect(() => {
    if (!hostRef.current || reducedMotion) return;
    let destroyed = false;
    let app: Application | null = null;

    async function boot() {
      if (!hostRef.current) return;
      const next = new Application();
      await next.init({ backgroundAlpha: 0, resizeTo: hostRef.current, antialias: true });
      if (destroyed || !hostRef.current) {
        next.destroy();
        return;
      }
      app = next;
      hostRef.current.appendChild(next.canvas);
      const graphics = new Graphics();
      next.stage.addChild(graphics);
      let t = 0;
      next.ticker.add(() => {
        t += 0.012;
        graphics.clear();
        const width = hostRef.current?.clientWidth ?? 1;
        const height = hostRef.current?.clientHeight ?? 1;
        const currentEdges = edgesRef.current;
        currentEdges.slice(0, 24).forEach((edge, index) => {
          const y = ((index + 1) / (currentEdges.length + 1)) * height;
          const pressure = Math.max(0.08, edge.backpressure);
          const x = ((t * (40 + edge.event_rate_1m * 6) + index * 53) % (width + 80)) - 40;
          graphics.circle(x, y, 2.5 + pressure * 8).fill({
            color: edge.health === "blocked" ? 0xff6b6b : edge.health === "degraded" ? 0xf6c56f : 0x68d391,
            alpha: 0.25 + pressure * 0.35
          });
        });
      });
    }

    boot();

    return () => {
      destroyed = true;
      app?.destroy(true);
    };
  }, [reducedMotion]);

  return <div className="particle-layer" ref={hostRef} aria-hidden="true" />;
}
