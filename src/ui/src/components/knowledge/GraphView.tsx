import React, { useEffect, useRef, useState } from 'react';
import { ZoomIn, ZoomOut, Maximize2 } from 'lucide-react';

interface Node {
  id: string;
  name: string;
  type: string;
  confidence: number;
  x: number;
  y: number;
  vx: number;
  vy: number;
  radius: number;
}

interface Edge {
  source: string;
  target: string;
  type: string;
  confidence: number;
}

interface GraphViewProps {
  entities: any[];
  relationships: any[];
  onNodeSelect: (nodeId: string) => void;
  selectedNodeId?: string;
}

export const GraphView: React.FC<GraphViewProps> = ({
  entities,
  relationships,
  onNodeSelect,
  selectedNodeId,
}) => {
  const svgRef = useRef<SVGSVGElement>(null);
  const containerRef = useRef<HTMLDivElement>(null);
  const [nodes, setNodes] = useState<Node[]>([]);
  const [edges, setEdges] = useState<Edge[]>([]);
  const [zoom, setZoom] = useState(1);
  const [pan, setPan] = useState({ x: 0, y: 0 });
  const [isDragging, setIsDragging] = useState(false);
  const [dragStart, setDragStart] = useState({ x: 0, y: 0 });
  const [hoveredNode, setHoveredNode] = useState<string | null>(null);
  const [dimensions, setDimensions] = useState({ width: 800, height: 600 });

  useEffect(() => {
    if (containerRef.current) {
      const { width, height } = containerRef.current.getBoundingClientRect();
      setDimensions({ width, height });
    }
  }, []);

  useEffect(() => {
    initializeGraph();
  }, [entities, relationships, dimensions]);

  const initializeGraph = () => {
    if (!entities || entities.length === 0) return;

    const centerX = dimensions.width / 2;
    const centerY = dimensions.height / 2;

    const connectionCounts = new Map<string, number>();
    relationships.forEach(rel => {
      connectionCounts.set(rel.source_entity, (connectionCounts.get(rel.source_entity) || 0) + 1);
      connectionCounts.set(rel.target_entity, (connectionCounts.get(rel.target_entity) || 0) + 1);
    });

    const initialNodes: Node[] = entities.map((entity, idx) => {
      const angle = (idx / entities.length) * 2 * Math.PI;
      const radius = Math.min(dimensions.width, dimensions.height) * 0.3;
      const connections = connectionCounts.get(entity.id) || 0;
      const nodeRadius = Math.max(8, Math.min(20, 8 + connections * 2));

      return {
        id: entity.id,
        name: entity.name,
        type: entity.type || 'unknown',
        confidence: entity.confidence || 0.5,
        x: centerX + Math.cos(angle) * radius,
        y: centerY + Math.sin(angle) * radius,
        vx: 0,
        vy: 0,
        radius: nodeRadius,
      };
    });

    const initialEdges: Edge[] = relationships.map(rel => ({
      source: rel.source_entity,
      target: rel.target_entity,
      type: rel.relation_type,
      confidence: rel.confidence || 0.5,
    }));

    setNodes(initialNodes);
    setEdges(initialEdges);

    simulateForces(initialNodes, initialEdges);
  };

  const simulateForces = (initialNodes: Node[], initialEdges: Edge[]) => {
    let currentNodes = [...initialNodes];
    const iterations = 100;
    const repulsionStrength = 2000;
    const attractionStrength = 0.01;
    const damping = 0.8;

    for (let iter = 0; iter < iterations; iter++) {
      currentNodes.forEach((node, i) => {
        let fx = 0;
        let fy = 0;

        currentNodes.forEach((other, j) => {
          if (i === j) return;
          const dx = node.x - other.x;
          const dy = node.y - other.y;
          const distSq = dx * dx + dy * dy + 1;
          const dist = Math.sqrt(distSq);
          const force = repulsionStrength / distSq;
          fx += (dx / dist) * force;
          fy += (dy / dist) * force;
        });

        initialEdges.forEach(edge => {
          if (edge.source === node.id) {
            const target = currentNodes.find(n => n.id === edge.target);
            if (target) {
              const dx = target.x - node.x;
              const dy = target.y - node.y;
              fx += dx * attractionStrength;
              fy += dy * attractionStrength;
            }
          } else if (edge.target === node.id) {
            const source = currentNodes.find(n => n.id === edge.source);
            if (source) {
              const dx = source.x - node.x;
              const dy = source.y - node.y;
              fx += dx * attractionStrength;
              fy += dy * attractionStrength;
            }
          }
        });

        const centerDx = dimensions.width / 2 - node.x;
        const centerDy = dimensions.height / 2 - node.y;
        fx += centerDx * 0.001;
        fy += centerDy * 0.001;

        node.vx = (node.vx + fx) * damping;
        node.vy = (node.vy + fy) * damping;
      });

      currentNodes.forEach(node => {
        node.x += node.vx;
        node.y += node.vy;

        node.x = Math.max(50, Math.min(dimensions.width - 50, node.x));
        node.y = Math.max(50, Math.min(dimensions.height - 50, node.y));
      });
    }

    setNodes(currentNodes);
  };

  const getNodeColor = (confidence: number): string => {
    if (confidence >= 0.7) return '#10b981';
    if (confidence >= 0.4) return '#f59e0b';
    return '#ef4444';
  };

  const handleWheel = (e: React.WheelEvent) => {
    e.preventDefault();
    const delta = e.deltaY > 0 ? 0.9 : 1.1;
    setZoom(prev => Math.max(0.3, Math.min(3, prev * delta)));
  };

  const handleMouseDown = (e: React.MouseEvent) => {
    if (e.target === svgRef.current || (e.target as Element).classList.contains('graph-background')) {
      setIsDragging(true);
      setDragStart({ x: e.clientX - pan.x, y: e.clientY - pan.y });
    }
  };

  const handleMouseMove = (e: React.MouseEvent) => {
    if (isDragging) {
      setPan({
        x: e.clientX - dragStart.x,
        y: e.clientY - dragStart.y,
      });
    }
  };

  const handleMouseUp = () => {
    setIsDragging(false);
  };

  const handleNodeClick = (nodeId: string) => {
    onNodeSelect(nodeId);
  };

  const resetView = () => {
    setZoom(1);
    setPan({ x: 0, y: 0 });
  };

  const connectedNodes = new Set<string>();
  if (selectedNodeId) {
    connectedNodes.add(selectedNodeId);
    edges.forEach(edge => {
      if (edge.source === selectedNodeId) connectedNodes.add(edge.target);
      if (edge.target === selectedNodeId) connectedNodes.add(edge.source);
    });
  }

  return (
    <div ref={containerRef} className="relative w-full h-full bg-slate-900 rounded-lg overflow-hidden">
      <svg
        ref={svgRef}
        width="100%"
        height="100%"
        onWheel={handleWheel}
        onMouseDown={handleMouseDown}
        onMouseMove={handleMouseMove}
        onMouseUp={handleMouseUp}
        onMouseLeave={handleMouseUp}
        className="cursor-move"
      >
        <rect width="100%" height="100%" fill="rgb(15 23 42)" className="graph-background" />
        
        <g transform={`translate(${pan.x}, ${pan.y}) scale(${zoom})`}>
          {/* Edges */}
          {edges.map((edge, idx) => {
            const sourceNode = nodes.find(n => n.id === edge.source);
            const targetNode = nodes.find(n => n.id === edge.target);
            if (!sourceNode || !targetNode) return null;

            const isHighlighted = selectedNodeId && 
              (edge.source === selectedNodeId || edge.target === selectedNodeId);
            const opacity = selectedNodeId ? (isHighlighted ? 0.8 : 0.1) : 0.3;

            return (
              <line
                key={`edge-${idx}`}
                x1={sourceNode.x}
                y1={sourceNode.y}
                x2={targetNode.x}
                y2={targetNode.y}
                stroke={getNodeColor(edge.confidence)}
                strokeWidth={isHighlighted ? 2 : 1}
                opacity={opacity}
              />
            );
          })}

          {/* Nodes */}
          {nodes.map(node => {
            const isSelected = node.id === selectedNodeId;
            const isConnected = connectedNodes.has(node.id);
            const opacity = selectedNodeId ? (isConnected ? 1 : 0.2) : 1;

            return (
              <g key={node.id}>
                <circle
                  cx={node.x}
                  cy={node.y}
                  r={node.radius}
                  fill={getNodeColor(node.confidence)}
                  stroke={isSelected ? '#3b82f6' : 'none'}
                  strokeWidth={isSelected ? 3 : 0}
                  opacity={opacity}
                  className="cursor-pointer hover:opacity-100 transition-opacity"
                  onClick={() => handleNodeClick(node.id)}
                  onMouseEnter={() => setHoveredNode(node.id)}
                  onMouseLeave={() => setHoveredNode(null)}
                />
                {(isSelected || hoveredNode === node.id) && (
                  <text
                    x={node.x}
                    y={node.y - node.radius - 8}
                    textAnchor="middle"
                    fill="#e2e8f0"
                    fontSize="12"
                    fontWeight="600"
                    className="pointer-events-none"
                  >
                    {node.name.length > 20 ? node.name.slice(0, 20) + '...' : node.name}
                  </text>
                )}
              </g>
            );
          })}
        </g>
      </svg>

      {/* Controls */}
      <div className="absolute top-4 right-4 flex flex-col gap-2">
        <button
          onClick={() => setZoom(prev => Math.min(3, prev * 1.2))}
          className="p-2 bg-slate-800 border border-slate-700 rounded-lg text-slate-300 hover:bg-slate-700 transition-colors"
          title="Zoom in"
        >
          <ZoomIn className="w-4 h-4" />
        </button>
        <button
          onClick={() => setZoom(prev => Math.max(0.3, prev * 0.8))}
          className="p-2 bg-slate-800 border border-slate-700 rounded-lg text-slate-300 hover:bg-slate-700 transition-colors"
          title="Zoom out"
        >
          <ZoomOut className="w-4 h-4" />
        </button>
        <button
          onClick={resetView}
          className="p-2 bg-slate-800 border border-slate-700 rounded-lg text-slate-300 hover:bg-slate-700 transition-colors"
          title="Reset view"
        >
          <Maximize2 className="w-4 h-4" />
        </button>
      </div>

      {/* Legend */}
      <div className="absolute bottom-4 left-4 bg-slate-800 border border-slate-700 rounded-lg p-3 space-y-2">
        <div className="text-xs font-semibold text-slate-300 mb-2">Confidence</div>
        <div className="flex items-center gap-2">
          <div className="w-3 h-3 rounded-full" style={{ backgroundColor: '#10b981' }} />
          <span className="text-xs text-slate-400">High (&gt;70%)</span>
        </div>
        <div className="flex items-center gap-2">
          <div className="w-3 h-3 rounded-full" style={{ backgroundColor: '#f59e0b' }} />
          <span className="text-xs text-slate-400">Medium (40-70%)</span>
        </div>
        <div className="flex items-center gap-2">
          <div className="w-3 h-3 rounded-full" style={{ backgroundColor: '#ef4444' }} />
          <span className="text-xs text-slate-400">Low (&lt;40%)</span>
        </div>
      </div>

      {/* Empty State */}
      {entities.length === 0 && (
        <div className="absolute inset-0 flex items-center justify-center">
          <div className="text-center">
            <div className="text-slate-400 text-lg mb-2">No entities to display</div>
            <div className="text-slate-500 text-sm">Select a topic to view its knowledge graph</div>
          </div>
        </div>
      )}
    </div>
  );
};
