interface StatusBadgeProps {
  status: string;
  size?: "sm" | "md";
}

const statusConfig: Record<string, { label: string; color: string; bg: string }> = {
  // agent status
  idle:              { label: "Idle",             color: "var(--mis-dim)",     bg: "rgba(107,114,128,0.15)" },
  running:           { label: "Running",          color: "var(--mis-cyan)",    bg: "rgba(34,211,238,0.12)" },
  paused:            { label: "Paused",           color: "#FBBF24",            bg: "rgba(251,191,36,0.12)" },
  error:             { label: "Error",            color: "var(--mis-warning)", bg: "rgba(231,111,81,0.15)" },
  disabled:          { label: "Disabled",         color: "var(--mis-muted)",   bg: "rgba(107,114,128,0.1)" },
  // task status
  backlog:           { label: "Backlog",          color: "var(--mis-dim)",     bg: "rgba(107,114,128,0.1)" },
  planned:           { label: "Planned",          color: "var(--mis-primary)", bg: "rgba(46,134,171,0.15)" },
  waiting_approval:  { label: "Awaiting Approval",color: "#FBBF24",            bg: "rgba(251,191,36,0.12)" },
  blocked:           { label: "Blocked",          color: "var(--mis-warning)", bg: "rgba(231,111,81,0.15)" },
  completed:         { label: "Completed",        color: "var(--mis-success)", bg: "rgba(42,157,143,0.15)" },
  failed:            { label: "Failed",           color: "#F87171",            bg: "rgba(248,113,113,0.15)" },
  canceled:          { label: "Canceled",         color: "var(--mis-muted)",   bg: "rgba(107,114,128,0.1)" },
  // approval
  pending:           { label: "Pending",          color: "#FBBF24",            bg: "rgba(251,191,36,0.12)" },
  approved:          { label: "Approved",         color: "var(--mis-success)", bg: "rgba(42,157,143,0.15)" },
  rejected:          { label: "Rejected",         color: "#F87171",            bg: "rgba(248,113,113,0.15)" },
  expired:           { label: "Expired",          color: "var(--mis-muted)",   bg: "rgba(107,114,128,0.1)" },
  // memory
  candidate:         { label: "Candidate",        color: "var(--mis-cyan)",    bg: "rgba(34,211,238,0.1)" },
  stale:             { label: "Stale",            color: "var(--mis-muted)",   bg: "rgba(107,114,128,0.1)" },
  superseded:        { label: "Superseded",       color: "var(--mis-muted)",   bg: "rgba(107,114,128,0.1)" },
  // connector
  ready:             { label: "Ready",            color: "var(--mis-success)", bg: "rgba(42,157,143,0.15)" },
  unavailable:       { label: "Unavailable",      color: "#F87171",            bg: "rgba(248,113,113,0.15)" },
  live:              { label: "Live",             color: "var(--mis-cyan)",    bg: "rgba(34,211,238,0.12)" },
  dry_run:           { label: "Dry-run",          color: "var(--mis-primary)", bg: "rgba(46,134,171,0.15)" },
  pending_approval:  { label: "Pending Approval", color: "#FBBF24",            bg: "rgba(251,191,36,0.12)" },
  // pass/fail
  pass:              { label: "Pass",             color: "var(--mis-success)", bg: "rgba(42,157,143,0.15)" },
  fail:              { label: "Fail",             color: "#F87171",            bg: "rgba(248,113,113,0.15)" },
};

export function StatusBadge({ status, size = "sm" }: StatusBadgeProps) {
  const cfg = statusConfig[status] ?? { label: status, color: "var(--mis-dim)", bg: "rgba(107,114,128,0.1)" };
  const px = size === "md" ? "px-2.5 py-1" : "px-2 py-0.5";
  const fs = size === "md" ? "text-xs" : "text-[11px]";

  return (
    <span
      className={`inline-flex items-center rounded font-medium ${px} ${fs}`}
      style={{ color: cfg.color, background: cfg.bg }}
    >
      {cfg.label}
    </span>
  );
}
