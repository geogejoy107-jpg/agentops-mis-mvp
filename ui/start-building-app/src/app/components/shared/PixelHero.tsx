import { useEffect, useRef } from "react";

// Zone definitions on the isometric grid
const ZONES = [
  { id: "tower",    label: "Control Tower",       x: 180, y: 40,  w: 100, h: 70,  color: "#22D3EE", glow: true  },
  { id: "registry", label: "Agent Registry",      x: 60,  y: 100, w: 90,  h: 55,  color: "#7A5AF8", glow: false },
  { id: "tasks",    label: "Task Board",          x: 300, y: 90,  w: 95,  h: 55,  color: "#2E86AB", glow: false },
  { id: "runtime",  label: "Runtime Lab",         x: 140, y: 155, w: 110, h: 65,  color: "#E76F51", glow: true  },
  { id: "tools",    label: "Tool Room",           x: 40,  y: 190, w: 80,  h: 50,  color: "#6B7280", glow: false },
  { id: "approval", label: "Approval Gate",       x: 310, y: 160, w: 85,  h: 50,  color: "#FBBF24", glow: true  },
  { id: "memory",   label: "Memory Library",      x: 80,  y: 265, w: 100, h: 55,  color: "#7A5AF8", glow: false },
  { id: "eval",     label: "Evaluation Room",     x: 210, y: 245, w: 95,  h: 55,  color: "#2A9D8F", glow: false },
  { id: "audit",    label: "Audit Vault",         x: 340, y: 230, w: 85,  h: 55,  color: "#EF4444", glow: true  },
  { id: "bases",    label: "External Base Dock",  x: 140, y: 335, w: 160, h: 55,  color: "#2A9D8F", glow: false },
];

// Agent definitions
const AGENTS = [
  { id: "research",  label: "Research",  color: "#22D3EE", startZone: "registry",  endZone: "tasks"   },
  { id: "coding",    label: "Coding",    color: "#7A5AF8", startZone: "tasks",     endZone: "runtime" },
  { id: "reviewer",  label: "Reviewer",  color: "#2A9D8F", startZone: "approval",  endZone: "eval"    },
  { id: "ops",       label: "Ops",       color: "#E76F51", startZone: "runtime",   endZone: "audit"   },
  { id: "connector", label: "Connector", color: "#2A9D8F", startZone: "bases",     endZone: "memory"  },
  { id: "curator",   label: "Curator",   color: "#C4B5FD", startZone: "memory",    endZone: "tower"   },
];

const FLOAT_METRICS = [
  { label: "Agents",      value: "16",       color: "#22D3EE", top: "8%",  left: "2%"  },
  { label: "Runs",        value: "6,043",    color: "#7A5AF8", top: "8%",  right: "2%" },
  { label: "Audit Logs",  value: "57,205",   color: "#EF4444", top: "40%", left: "1%"  },
  { label: "Mem Cands",   value: "3,003",    color: "#C4B5FD", top: "40%", right: "1%" },
  { label: "Total Cost",  value: "$2.22",    color: "#2A9D8F", top: "72%", left: "1%"  },
  { label: "Approvals",   value: "2 pending",color: "#FBBF24", top: "72%", right: "1%" },
];

const CONNECTORS = [
  { label: "OpenClaw",       status: "Ready",    color: "#2A9D8F", pulse: false },
  { label: "Agnesfallback",  status: "Live",     color: "#22D3EE", pulse: true  },
  { label: "Notion",         status: "Dry-run",  color: "#2E86AB", pulse: false },
];

function zoneCenter(zoneId: string) {
  const z = ZONES.find(z => z.id === zoneId)!;
  return { x: z.x + z.w / 2, y: z.y + z.h / 2 };
}

// Pixel agent sprite — a tiny 10×14 character
function AgentSprite({ color, x, y }: { color: string; x: number; y: number }) {
  return (
    <g transform={`translate(${x - 5}, ${y - 12})`}>
      {/* Head */}
      <rect x={3} y={0} width={4} height={4} fill={color} />
      {/* Body */}
      <rect x={2} y={4} width={6} height={5} fill={color} opacity={0.85} />
      {/* Legs */}
      <rect x={2} y={9} width={2} height={3} fill={color} opacity={0.7} />
      <rect x={6} y={9} width={2} height={3} fill={color} opacity={0.7} />
    </g>
  );
}

export function PixelHero() {
  const agentRefs = useRef<Record<string, SVGGElement | null>>({});

  // Animate agents between zones using GSAP-free CSS approach
  // We encode the animation in inline style keyframes per agent
  const getAgentStyle = (agent: typeof AGENTS[number], idx: number): React.CSSProperties => {
    const from = zoneCenter(agent.startZone);
    const to = zoneCenter(agent.endZone);
    return {
      animationName: `move-agent-${agent.id}`,
      animationDuration: `${4 + idx * 0.7}s`,
      animationTimingFunction: "linear",
      animationIterationCount: "infinite",
      animationDelay: `${idx * 1.1}s`,
      offsetPath: `path("M ${from.x} ${from.y} L ${to.x} ${to.y}")`,
    } as React.CSSProperties;
  };

  return (
    <div
      className="relative w-full overflow-hidden rounded-2xl"
      style={{
        height: 300,
        background: "linear-gradient(135deg, #0B1020 0%, #0f1a30 60%, #111827 100%)",
        border: "1px solid var(--mis-border)",
      }}
    >
      {/* Grid background dots */}
      <svg
        className="absolute inset-0 w-full h-full opacity-10"
        style={{ pointerEvents: "none" }}
      >
        <defs>
          <pattern id="grid" width="20" height="20" patternUnits="userSpaceOnUse">
            <circle cx="1" cy="1" r="1" fill="#22D3EE" />
          </pattern>
        </defs>
        <rect width="100%" height="100%" fill="url(#grid)" />
      </svg>

      {/* Isometric stage */}
      <div
        className="absolute"
        style={{
          top: "50%",
          left: "50%",
          transform: "translate(-50%, -52%) rotateX(50deg) rotateZ(-30deg) scale(0.78)",
          transformOrigin: "center center",
          transformStyle: "preserve-3d",
          width: 460,
          height: 420,
        }}
      >
        <svg width={460} height={420} style={{ overflow: "visible" }}>
          <defs>
            {/* Glow filters */}
            <filter id="glow-cyan" x="-30%" y="-30%" width="160%" height="160%">
              <feGaussianBlur stdDeviation="4" result="blur" />
              <feMerge><feMergeNode in="blur" /><feMergeNode in="SourceGraphic" /></feMerge>
            </filter>
            <filter id="glow-orange" x="-30%" y="-30%" width="160%" height="160%">
              <feGaussianBlur stdDeviation="5" result="blur" />
              <feMerge><feMergeNode in="blur" /><feMergeNode in="SourceGraphic" /></feMerge>
            </filter>
            <filter id="glow-red" x="-30%" y="-30%" width="160%" height="160%">
              <feGaussianBlur stdDeviation="4" result="blur" />
              <feMerge><feMergeNode in="blur" /><feMergeNode in="SourceGraphic" /></feMerge>
            </filter>

            {/* Agent animations */}
            {AGENTS.map((agent, idx) => {
              const from = zoneCenter(agent.startZone);
              const to = zoneCenter(agent.endZone);
              return (
                <style key={agent.id}>{`
                  @keyframes walk-${agent.id} {
                    0%   { transform: translate(${from.x}px, ${from.y}px); }
                    45%  { transform: translate(${to.x}px,   ${to.y}px);   }
                    55%  { transform: translate(${to.x}px,   ${to.y}px);   }
                    100% { transform: translate(${from.x}px, ${from.y}px); }
                  }
                  .agent-${agent.id} {
                    animation: walk-${agent.id} ${5 + idx * 0.8}s ${idx * 1.3}s linear infinite;
                  }
                `}</style>
              );
            })}

            {/* Glow pulse for zones */}
            <style>{`
              @keyframes pulse-glow {
                0%, 100% { opacity: 0.5; }
                50%       { opacity: 1;   }
              }
              @keyframes blink-yellow {
                0%, 100% { fill: #FBBF24; opacity: 0.6; }
                50%       { fill: #FDE68A; opacity: 1;   }
              }
              @keyframes tower-pulse {
                0%, 100% { r: 4; opacity: 0.9; }
                50%       { r: 7; opacity: 0.4; }
              }
            `}</style>
          </defs>

          {/* Platform base shadow */}
          <ellipse cx={230} cy={400} rx={200} ry={24} fill="#000" opacity={0.35} />

          {/* Connector lines between zones */}
          {[
            ["registry", "tasks"], ["tasks", "runtime"], ["runtime", "approval"],
            ["tools", "runtime"], ["approval", "eval"], ["eval", "audit"],
            ["memory", "eval"], ["bases", "memory"], ["tower", "registry"],
          ].map(([a, b]) => {
            const ca = zoneCenter(a);
            const cb = zoneCenter(b);
            return (
              <line
                key={`${a}-${b}`}
                x1={ca.x} y1={ca.y} x2={cb.x} y2={cb.y}
                stroke="#1F2937" strokeWidth={1.5} strokeDasharray="4 4"
              />
            );
          })}

          {/* Zone tiles */}
          {ZONES.map(zone => {
            const filterMap: Record<string, string> = {
              "#22D3EE": "url(#glow-cyan)",
              "#E76F51": "url(#glow-orange)",
              "#EF4444": "url(#glow-red)",
            };
            const glowFilter = zone.glow ? (filterMap[zone.color] ?? undefined) : undefined;

            return (
              <g key={zone.id} filter={glowFilter}>
                {/* Zone shadow */}
                <rect
                  x={zone.x + 3} y={zone.y + 5}
                  width={zone.w} height={zone.h}
                  rx={3} fill="#000" opacity={0.3}
                />
                {/* Zone body */}
                <rect
                  x={zone.x} y={zone.y}
                  width={zone.w} height={zone.h}
                  rx={3}
                  fill={zone.color}
                  fillOpacity={0.1}
                  stroke={zone.color}
                  strokeWidth={zone.id === "approval" ? 0 : 1}
                  strokeOpacity={0.6}
                />
                {/* Approval gate blink */}
                {zone.id === "approval" && (
                  <rect
                    x={zone.x} y={zone.y}
                    width={zone.w} height={zone.h}
                    rx={3}
                    fill="#FBBF24" fillOpacity={0.08}
                    stroke="#FBBF24" strokeWidth={1.5}
                    style={{ animation: "blink-yellow 1.4s ease-in-out infinite" }}
                  />
                )}
                {/* Top accent bar */}
                <rect
                  x={zone.x} y={zone.y}
                  width={zone.w} height={4}
                  rx={3} fill={zone.color} fillOpacity={0.7}
                />
                {/* Label */}
                <text
                  x={zone.x + zone.w / 2}
                  y={zone.y + zone.h / 2 + 1}
                  textAnchor="middle"
                  fontSize={7}
                  fontFamily="monospace"
                  fill={zone.color}
                  fillOpacity={0.9}
                  style={{ userSelect: "none" }}
                >
                  {zone.label}
                </text>
                {/* Status dot */}
                {zone.id === "tower" && (
                  <circle
                    cx={zone.x + zone.w - 10}
                    cy={zone.y + 12}
                    r={4}
                    fill="#22D3EE"
                    style={{ animation: "tower-pulse 2s ease-in-out infinite" }}
                  />
                )}
                {/* External base dots */}
                {zone.id === "bases" && (
                  <>
                    {["#2A9D8F", "#E76F51", "#7A5AF8", "#FBBF24"].map((c, i) => (
                      <circle key={i} cx={zone.x + 20 + i * 30} cy={zone.y + zone.h - 14} r={5} fill={c} fillOpacity={0.8} />
                    ))}
                  </>
                )}
              </g>
            );
          })}

          {/* Animated agents */}
          {AGENTS.map((agent) => {
            const from = zoneCenter(agent.startZone);
            return (
              <g
                key={agent.id}
                className={`agent-${agent.id}`}
                style={{ transformOrigin: `${from.x}px ${from.y}px` }}
              >
                <AgentSprite color={agent.color} x={0} y={0} />
              </g>
            );
          })}
        </svg>
      </div>

      {/* Floating metric chips */}
      {FLOAT_METRICS.map(m => (
        <div
          key={m.label}
          className="absolute flex flex-col items-center px-2.5 py-1.5 rounded-lg"
          style={{
            top: m.top,
            left: "left" in m ? (m as any).left : undefined,
            right: "right" in m ? (m as any).right : undefined,
            background: "rgba(17,24,39,0.85)",
            border: `1px solid ${m.color}30`,
            backdropFilter: "blur(4px)",
            minWidth: 70,
          }}
        >
          <div className="text-[10px] uppercase tracking-wide" style={{ color: "var(--mis-muted)" }}>{m.label}</div>
          <div className="text-sm font-semibold" style={{ color: m.color }}>{m.value}</div>
        </div>
      ))}

      {/* Bottom connector status strip */}
      <div
        className="absolute bottom-3 left-1/2 flex items-center gap-3 px-4 py-2 rounded-lg"
        style={{
          transform: "translateX(-50%)",
          background: "rgba(17,24,39,0.9)",
          border: "1px solid var(--mis-border)",
          backdropFilter: "blur(6px)",
        }}
      >
        {CONNECTORS.map(c => (
          <div key={c.label} className="flex items-center gap-1.5">
            <span
              className="w-2 h-2 rounded-full"
              style={{
                background: c.color,
                boxShadow: c.pulse ? `0 0 6px ${c.color}` : "none",
                animation: c.pulse ? "tower-pulse 1.5s ease-in-out infinite" : "none",
              }}
            />
            <span className="text-[11px]" style={{ color: "var(--mis-dim)" }}>{c.label}</span>
            <span className="text-[10px] font-medium" style={{ color: c.color }}>{c.status}</span>
          </div>
        ))}
      </div>

      {/* Title overlay */}
      <div
        className="absolute top-4 left-1/2 text-center"
        style={{ transform: "translateX(-50%)" }}
      >
        <div className="text-[11px] font-semibold tracking-widest uppercase" style={{ color: "var(--mis-cyan)" }}>
          AI Workforce Operating Floor
        </div>
        <div className="text-[10px] mt-0.5" style={{ color: "var(--mis-muted)" }}>
          AgentOps MIS · v1.2.2 · 6 agents active
        </div>
      </div>
    </div>
  );
}
