import { useState } from "react";
import { ClipboardList, User, Bot, Monitor } from "lucide-react";
import { auditLogs } from "../../data/mockData";
import type { ActorType } from "../../data/mockData";

type ActorFilter = "all" | ActorType;

const ACTOR_COLOR: Record<ActorType, string> = {
  user:   "var(--mis-purple)",
  agent:  "var(--mis-cyan)",
  system: "var(--mis-muted)",
};

function ActorIcon({ type }: { type: ActorType }) {
  const color = ACTOR_COLOR[type];
  const Icon = type === "user" ? User : type === "agent" ? Bot : Monitor;
  return (
    <span
      className="inline-flex w-6 h-6 rounded-full items-center justify-center shrink-0"
      style={{ background: `${color}18`, color }}
    >
      <Icon size={11} />
    </span>
  );
}

export function AuditCenter() {
  const [actorFilter, setActorFilter] = useState<ActorFilter>("all");

  const filtered = actorFilter === "all" ? auditLogs : auditLogs.filter(l => l.actor_type === actorFilter);

  return (
    <div className="space-y-5 w-full">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-lg font-semibold" style={{ color: "var(--mis-text)" }}>Audit Center</h1>
          <p className="text-xs mt-0.5" style={{ color: "var(--mis-dim)" }}>
            {auditLogs.length} audit events · tamper-chain verified
          </p>
        </div>
        <div
          className="flex items-center gap-1.5 text-[11px] px-3 py-1.5 rounded-lg"
          style={{ background: "rgba(42,157,143,0.1)", color: "var(--mis-success)", border: "1px solid rgba(42,157,143,0.2)" }}
        >
          <ClipboardList size={12} />
          Chain intact
        </div>
      </div>

      {/* Actor filter */}
      <div className="flex gap-2">
        {(["all", "user", "agent", "system"] as ActorFilter[]).map(f => {
          const color = f === "all" ? "var(--mis-dim)" : ACTOR_COLOR[f as ActorType];
          return (
            <button
              key={f}
              onClick={() => setActorFilter(f)}
              className="text-[11px] px-3 py-1.5 rounded-lg capitalize transition-all"
              style={{
                background: actorFilter === f ? `${color}18` : "var(--mis-surface)",
                color: actorFilter === f ? color : "var(--mis-dim)",
                border: `1px solid ${actorFilter === f ? `${color}30` : "var(--mis-border)"}`,
              }}
            >
              {f} <span className="opacity-60">({f === "all" ? auditLogs.length : auditLogs.filter(l => l.actor_type === f).length})</span>
            </button>
          );
        })}
      </div>

      {/* Audit log table */}
      <div className="rounded-xl overflow-hidden" style={{ background: "var(--mis-surface)", border: "1px solid var(--mis-border)" }}>
        <table className="w-full text-xs">
          <thead>
            <tr style={{ background: "var(--mis-surface2)", color: "var(--mis-muted)" }}>
              {["Actor", "Action", "Entity", "Entity ID", "Timestamp"].map(h => (
                <th key={h} className="text-left px-4 py-3 font-medium">{h}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {filtered.map((log, i) => (
              <tr
                key={log.audit_id}
                style={{
                  color: "var(--mis-dim)",
                  borderTop: i > 0 ? "1px solid var(--mis-border)" : "none",
                }}
              >
                <td className="px-4 py-3">
                  <div className="flex items-center gap-2">
                    <ActorIcon type={log.actor_type} />
                    <div>
                      <div className="font-medium text-[11px]" style={{ color: "var(--mis-text)" }}>{log.actor_id}</div>
                      <div className="text-[10px] capitalize" style={{ color: ACTOR_COLOR[log.actor_type] }}>{log.actor_type}</div>
                    </div>
                  </div>
                </td>
                <td className="px-4 py-3">
                  <span className="font-medium" style={{ color: "var(--mis-text)" }}>{log.action}</span>
                </td>
                <td className="px-4 py-3 capitalize">{log.entity_type}</td>
                <td className="px-4 py-3 font-mono text-[11px]">{log.entity_id}</td>
                <td className="px-4 py-3 text-[11px]" style={{ color: "var(--mis-muted)" }}>
                  {new Date(log.created_at).toLocaleString()}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
