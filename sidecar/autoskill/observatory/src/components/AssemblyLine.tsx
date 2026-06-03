import { useEffect, useMemo, useState } from "react";
import {
  Background,
  Controls,
  MiniMap,
  Position,
  ReactFlow,
  type Edge,
  type Node,
  type NodeMouseHandler
} from "@xyflow/react";
import type { PipelineEdge, Station } from "../types";

type Props = {
  stations: Station[];
  edges: PipelineEdge[];
  selectedId?: string;
  onSelect: (station: Station) => void;
};

function healthColor(health: string) {
  switch (health) {
    case "healthy":
      return "#68d391";
    case "degraded":
      return "#f6c56f";
    case "blocked":
      return "#ff6b6b";
    case "frozen":
      return "#8bd3ff";
    case "offline":
      return "#9aa4b2";
    default:
      return "#c4a7ff";
  }
}

export function AssemblyLine({ stations, edges, selectedId, onSelect }: Props) {
  const [nodes, setNodes] = useState<Node[]>([]);
  const flowEdges = useMemo<Edge[]>(
    () =>
      edges.map((edge) => ({
        id: edge.edge_id,
        source: edge.from,
        target: edge.to,
        animated: edge.event_rate_1m > 0 || edge.backpressure > 0,
        label: edge.dominant_item_kind,
        style: {
          stroke: healthColor(edge.health),
          strokeWidth: Math.max(1.5, Math.min(8, edge.event_rate_1m + edge.backpressure * 8))
        },
        labelStyle: { fill: "#cdd6e3", fontSize: 10 }
      })),
    [edges]
  );

  useEffect(() => {
    let cancelled = false;

    async function layout() {
      const { default: ELK } = await import("elkjs/lib/elk.bundled.js");
      const elk = new ELK();
      const graph = {
        id: "root",
        layoutOptions: {
          "elk.algorithm": "layered",
          "elk.direction": "RIGHT",
          "elk.layered.spacing.nodeNodeBetweenLayers": "68",
          "elk.spacing.nodeNode": "38"
        },
        children: stations.map((station) => ({
          id: station.component_id,
          width: 230,
          height: 116
        })),
        edges: edges.map((edge) => ({
          id: edge.edge_id,
          sources: [edge.from],
          targets: [edge.to]
        }))
      };
      const layouted = await elk.layout(graph);
      if (cancelled) return;
      const nextNodes =
        layouted.children?.map((node) => {
          const station = stations.find((item) => item.component_id === node.id)!;
          return {
            id: station.component_id,
            position: { x: node.x ?? 0, y: node.y ?? 0 },
            data: {
              station,
              label: <StationCard station={station} />
            },
            className: `station-node health-${station.health} ${
              selectedId === station.component_id ? "is-selected" : ""
            }`,
            type: "default",
            sourcePosition: Position.Right,
            targetPosition: Position.Left
          } satisfies Node;
        }) ?? [];
      setNodes(nextNodes);
    }

    void layout();
    return () => {
      cancelled = true;
    };
  }, [edges, selectedId, stations]);

  const handleNodeClick: NodeMouseHandler = (_, node) => {
    const station = stations.find((item) => item.component_id === node.id);
    if (station) onSelect(station);
  };

  return (
    <div className="assembly-line" aria-label="SkillKernel pipeline assembly line">
      <ReactFlow
        nodes={nodes}
        edges={flowEdges}
        fitView
        minZoom={0.2}
        maxZoom={1.4}
        onNodeClick={handleNodeClick}
        nodesDraggable={false}
        elementsSelectable
      >
        <MiniMap
          pannable
          zoomable
          nodeColor={(node) => healthColor((node.data as { station: Station }).station.health)}
        />
        <Controls showInteractive={false} />
        <Background color="#30404f" gap={28} />
      </ReactFlow>
    </div>
  );
}

function StationCard({ station }: { station: Station }) {
  return (
    <div className="station-card">
      <div className="station-card__top">
        <span className={`status-dot health-${station.health}`} />
        <strong>{station.display_name}</strong>
      </div>
      <p>{station.purpose}</p>
      <div className="station-card__metrics">
        <span>{station.input_rate_1m.toFixed(1)} in/min</span>
        <span>{station.queue_depth} queued</span>
        <span>{station.p95_latency_ms.toFixed(0)} ms p95</span>
      </div>
    </div>
  );
}
