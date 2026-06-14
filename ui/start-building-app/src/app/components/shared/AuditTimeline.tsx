import { User, Bot, Monitor } from "lucide-react";
import type { AuditLog } from "../../data/mockData";

interface AuditTimelineProps {
  logs: AuditLog[];
}

function ActorIcon({ type }: { type: string }) {
  if (type === "user") return <User size={12} />;
  if (type === "agent") return <Bot size={12} />;
  return <Monitor size={12} />;
}

const actorColor: Record<string, string> = {
  user:   "var(--mis-purple)",
  agent:  "var(--mis-cyan)",
  system: "var(--mis-muted)",
};

export function AuditTimeline({ logs }: AuditTimelineProps) {
  return (
    <div className="space-y-0">
      {logs.map((log, idx) => (
        <div key={log.audit_id} className="flex gap-3">
          {/* Timeline line */}
          <div className="flex flex-col items-center">
            <div
              className="w-6 h-6 rounded-full flex items-center justify-center shrink-0"
              style={{ background: `${actorColor[log.actor_type]}18`, color: actorColor[log.actor_type] }}
            >
              <ActorIcon type={log.actor_type} />
            </div>
            {idx < logs.length - 1 && (
              <div className="w-px flex-1 my-1" style={{ background: "var(--mis-border)" }} />
            )}
          </div>

          {/* Content */}
          <div className="pb-4 min-w-0">
            <div className="flex items-baseline gap-2">
              <span className="text-xs font-medium" style={{ color: "var(--mis-text)" }}>
                {log.action}
              </span>
              <span className="text-[10px]" style={{ color: "var(--mis-muted)" }}>
                {log.actor_id}
              </span>
            </div>
            <div className="text-[11px] mt-0.5" style={{ color: "var(--mis-dim)" }}>
              {log.entity_type}: {log.entity_id}
            </div>
            <div className="text-[10px] mt-0.5" style={{ color: "var(--mis-muted)" }}>
              {new Date(log.created_at).toLocaleString()}
            </div>
          </div>
        </div>
      ))}
    </div>
  );
}
