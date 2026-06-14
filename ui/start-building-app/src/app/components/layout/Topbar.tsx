import { Search, Bell, ChevronDown, Radio } from "lucide-react";

export function Topbar() {
  return (
    <header
      className="flex items-center justify-between px-5 h-12 shrink-0 border-b"
      style={{
        background: "var(--mis-surface)",
        borderColor: "var(--mis-border)",
      }}
    >
      {/* Left: workspace switcher */}
      <button
        className="flex items-center gap-1.5 text-xs rounded px-2 py-1 hover:opacity-80 transition-opacity"
        style={{ color: "var(--mis-text)", background: "var(--mis-surface2)" }}
      >
        <span style={{ color: "var(--mis-dim)" }}>Workspace:</span>
        AgentOps Demo
        <ChevronDown size={12} style={{ color: "var(--mis-dim)" }} />
      </button>

      {/* Center: search */}
      <div
        className="flex items-center gap-2 px-3 py-1.5 rounded text-xs w-64"
        style={{ background: "var(--mis-surface2)", color: "var(--mis-dim)" }}
      >
        <Search size={13} />
        <span>Search agents, tasks, runs…</span>
      </div>

      {/* Right */}
      <div className="flex items-center gap-3">
        {/* Live mode badge */}
        <div
          className="flex items-center gap-1.5 px-2 py-1 rounded text-[11px] font-medium"
          style={{ background: "rgba(42,157,143,0.15)", color: "var(--mis-success)" }}
        >
          <Radio size={11} className="animate-pulse" />
          Live
        </div>

        {/* Notifications */}
        <button
          className="relative p-1.5 rounded hover:opacity-80"
          style={{ color: "var(--mis-dim)" }}
        >
          <Bell size={15} />
          <span
            className="absolute top-0.5 right-0.5 w-2 h-2 rounded-full"
            style={{ background: "var(--mis-warning)" }}
          />
        </button>

        {/* Avatar */}
        <div
          className="w-7 h-7 rounded-full flex items-center justify-center text-[11px] font-semibold cursor-pointer"
          style={{ background: "var(--mis-purple)", color: "#fff" }}
          title="Jiwu Wang"
        >
          JW
        </div>
      </div>
    </header>
  );
}
