import { useEffect, useMemo, useState } from "react";
import {
  Background,
  BaseEdge,
  Controls,
  EdgeLabelRenderer,
  MiniMap,
  MarkerType,
  Position,
  ReactFlow,
  type Edge,
  type EdgeProps,
  type EdgeTypes,
  type Node,
  type NodeMouseHandler,
  getSmoothStepPath
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

function pressureLabel(edge: PipelineEdge) {
  const pressure = Math.round(edge.backpressure * 100);
  if (pressure > 0) return `${edge.dominant_item_kind} / ${pressure}%`;
  return edge.dominant_item_kind;
}

const labelLaneOffsets = [-18, 18, -32, 32, -46, 46];

function labelOffsetForEdge(index: number) {
  return {
    x: index % 2 === 0 ? -8 : 8,
    y: labelLaneOffsets[index % labelLaneOffsets.length]
  };
}

type PipelineFlowEdgeData = Record<string, unknown> & {
  health: string;
  label: string;
  labelOffsetX: number;
  labelOffsetY: number;
};

type PipelineFlowEdgeType = Edge<PipelineFlowEdgeData, "pipeline">;

function PipelineFlowEdge({
  data,
  id,
  interactionWidth,
  markerEnd,
  sourcePosition,
  sourceX,
  sourceY,
  style,
  targetPosition,
  targetX,
  targetY
}: EdgeProps<PipelineFlowEdgeType>) {
  const [edgePath, , labelY] = getSmoothStepPath({
    sourcePosition,
    sourceX,
    sourceY,
    targetPosition,
    targetX,
    targetY,
    borderRadius: 18
  });
  const label = data?.label ?? "";
  const labelX = sourceX + (targetX - sourceX) / 2 + (data?.labelOffsetX ?? 0);
  const adjustedLabelY = labelY + (data?.labelOffsetY ?? 0);

  return (
    <>
      <BaseEdge
        className={`pipeline-edge__path health-${data?.health ?? "unknown"}`}
        id={id}
        interactionWidth={interactionWidth}
        markerEnd={markerEnd}
        path={edgePath}
        style={style}
      />
      <EdgeLabelRenderer>
        <div
          className={`pipeline-edge-label pipeline-edge-label--${data?.health ?? "unknown"}`}
          style={{ transform: `translate(-50%, -50%) translate(${labelX}px, ${adjustedLabelY}px)` }}
          title={label}
        >
          {label}
        </div>
      </EdgeLabelRenderer>
    </>
  );
}

const edgeTypes = { pipeline: PipelineFlowEdge } satisfies EdgeTypes;

export function AssemblyLine({ stations, edges, selectedId, onSelect }: Props) {
  const [nodes, setNodes] = useState<Node[]>([]);
  const stationById = useMemo(
    () => new Map(stations.map((station) => [station.component_id, station])),
    [stations]
  );
  const structuralKey = useMemo(
    () =>
      JSON.stringify({
        stations: stations.map((station) => station.component_id),
        edges: edges.map((edge) => [edge.edge_id, edge.from, edge.to])
      }),
    [edges, stations]
  );
  const flowEdges = useMemo<Edge[]>(
    () =>
      edges.map((edge, index) => {
        const labelOffset = labelOffsetForEdge(index);
        return {
          id: edge.edge_id,
          source: edge.from,
          target: edge.to,
          type: "pipeline",
          animated: edge.event_rate_1m > 0 || edge.backpressure > 0,
          data: {
            health: edge.health,
            label: pressureLabel(edge),
            labelOffsetX: labelOffset.x,
            labelOffsetY: labelOffset.y
          },
          className: `pipeline-edge health-${edge.health}`,
          style: {
            stroke: healthColor(edge.health),
            strokeWidth: Math.max(1.4, Math.min(5.5, 1.4 + edge.event_rate_1m * 0.28 + edge.backpressure * 5)),
            opacity: edge.health === "healthy" ? 0.78 : 0.92
          },
          markerEnd: {
            type: MarkerType.ArrowClosed,
            color: healthColor(edge.health),
            width: 18,
            height: 18
          },
          interactionWidth: 18
        };
      }),
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
          "elk.edgeRouting": "ORTHOGONAL",
          "elk.layered.spacing.edgeEdgeBetweenLayers": "26",
          "elk.layered.spacing.edgeNodeBetweenLayers": "34",
          "elk.layered.spacing.nodeNodeBetweenLayers": "184",
          "elk.spacing.edgeEdge": "18",
          "elk.spacing.edgeNode": "28",
          "elk.spacing.nodeNode": "66"
        },
        children: stations.map((station) => ({
          id: station.component_id,
          width: 264,
          height: 136
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
  }, [structuralKey]);

  useEffect(() => {
    setNodes((current) =>
      current.map((node) => {
        const station = stationById.get(node.id);
        if (!station) return node;
        return {
          ...node,
          data: {
            station,
            label: <StationCard station={station} />
          },
          className: `station-node health-${station.health} ${
            selectedId === station.component_id ? "is-selected" : ""
          }`
        };
      })
    );
  }, [selectedId, stationById]);

  const handleNodeClick: NodeMouseHandler = (_, node) => {
    const station = stations.find((item) => item.component_id === node.id);
    if (station) onSelect(station);
  };

  return (
    <div className="assembly-line" aria-label="SkillKernel pipeline assembly line">
      <ReactFlow
        nodes={nodes}
        edges={flowEdges}
        edgeTypes={edgeTypes}
        defaultViewport={{ x: 28, y: 92, zoom: 0.42 }}
        minZoom={0.2}
        maxZoom={1.4}
        onNodeClick={handleNodeClick}
        nodesDraggable={false}
        elementsSelectable
      >
        <MiniMap
          pannable
          zoomable
          maskColor="rgba(5, 9, 12, 0.62)"
          style={{ width: 150, height: 104, background: "rgba(13, 17, 20, 0.84)" }}
          nodeColor={(node) => healthColor((node.data as { station: Station }).station.health)}
        />
        <Controls showInteractive={false} />
        <Background color="#2d3944" gap={32} />
      </ReactFlow>
    </div>
  );
}

function compactMetric(value: number, fractionDigits = 1) {
  if (!Number.isFinite(value)) return "0";
  return new Intl.NumberFormat("en", {
    maximumFractionDigits: Math.abs(value) < 10 ? fractionDigits : 0,
    notation: Math.abs(value) >= 10000 ? "compact" : "standard"
  }).format(value);
}

function StationCard({ station }: { station: Station }) {
  const activeFlow = Math.max(station.input_rate_1m, station.output_rate_1m);

  return (
    <div className="station-card">
      <div className="station-card__top">
        <span className={`status-dot health-${station.health}`} aria-hidden="true" />
        <div>
          <strong>{station.display_name}</strong>
          <span>{station.mode}</span>
        </div>
      </div>
      <p>{station.purpose}</p>
      <div className="station-card__metrics">
        <span>
          <strong>{compactMetric(activeFlow)}</strong>
          <small>flow</small>
        </span>
        <span>
          <strong>{compactMetric(station.queue_depth, 0)}</strong>
          <small>queued</small>
        </span>
        <span>
          <strong>{compactMetric(station.p95_latency_ms, 0)}</strong>
          <small>ms p95</small>
        </span>
      </div>
    </div>
  );
}
