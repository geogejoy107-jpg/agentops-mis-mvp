import { useState } from "react";
import { NavLink, useLocation } from "react-router";
import {
  Home, CheckSquare, Bot, ShieldCheck, Brain, BarChart2, Package,
  Activity, BookOpen, List, Wrench, Plug, Database, FileText, ClipboardList,
  ChevronDown, ChevronRight, Zap,
} from "lucide-react";

interface NavItem {
  label: string;
  path: string;
  icon: React.ReactNode;
}

interface NavGroup {
  title: string;
  items: NavItem[];
}

const navGroups: NavGroup[] = [
  {
    title: "Client Workspace",
    items: [
      { label: "Home",         path: "/workspace",          icon: <Home size={15} /> },
      { label: "My Tasks",     path: "/workspace/tasks",    icon: <CheckSquare size={15} /> },
      { label: "AI Employees", path: "/workspace/agents",   icon: <Bot size={15} /> },
      { label: "Approvals",    path: "/workspace/approvals",icon: <ShieldCheck size={15} /> },
      { label: "Memory",       path: "/workspace/memory",   icon: <Brain size={15} /> },
      { label: "Reports",      path: "/workspace/reports",  icon: <BarChart2 size={15} /> },
      { label: "Templates",    path: "/admin/templates",    icon: <Package size={15} /> },
    ],
  },
  {
    title: "Admin Console",
    items: [
      { label: "Control Tower",  path: "/admin",                    icon: <Activity size={15} /> },
      { label: "Agent Registry", path: "/workspace/agents",         icon: <Bot size={15} /> },
      { label: "Run Ledger",     path: "/admin/runs/run_001",       icon: <List size={15} /> },
      { label: "Tool Calls",     path: "/admin/toolcalls",          icon: <Wrench size={15} /> },
      { label: "Connectors",     path: "/admin/connectors",         icon: <Plug size={15} /> },
      { label: "External Bases", path: "/admin/bases/notion",       icon: <Database size={15} /> },
      { label: "Audit",          path: "/admin/audit",              icon: <ClipboardList size={15} /> },
    ],
  },
];

export function Sidebar() {
  const location = useLocation();
  const [collapsed, setCollapsed] = useState<Record<string, boolean>>({});

  const toggleGroup = (title: string) => {
    setCollapsed((prev) => ({ ...prev, [title]: !prev[title] }));
  };

  return (
    <aside
      className="flex flex-col w-56 shrink-0 h-full border-r"
      style={{
        background: "var(--mis-surface)",
        borderColor: "var(--mis-border)",
      }}
    >
      {/* Logo */}
      <div
        className="flex items-center gap-2 px-4 py-4 border-b"
        style={{ borderColor: "var(--mis-border)" }}
      >
        <div
          className="w-7 h-7 rounded flex items-center justify-center"
          style={{ background: "var(--mis-cyan)", color: "#0B1020" }}
        >
          <Zap size={14} />
        </div>
        <div>
          <div className="text-xs font-semibold leading-tight" style={{ color: "var(--mis-text)" }}>
            AgentOps MIS
          </div>
          <div className="text-[10px] leading-tight" style={{ color: "var(--mis-dim)" }}>
            v1.2.2
          </div>
        </div>
      </div>

      {/* Nav */}
      <nav className="flex-1 overflow-y-auto py-3 px-2 space-y-4">
        {navGroups.map((group) => {
          const isCollapsed = collapsed[group.title];
          return (
            <div key={group.title}>
              <button
                onClick={() => toggleGroup(group.title)}
                className="flex items-center justify-between w-full px-2 py-1 rounded text-[10px] font-semibold tracking-wider uppercase mb-1 hover:opacity-80 transition-opacity"
                style={{ color: "var(--mis-muted)" }}
              >
                {group.title}
                {isCollapsed ? <ChevronRight size={11} /> : <ChevronDown size={11} />}
              </button>

              {!isCollapsed && (
                <ul className="space-y-0.5">
                  {group.items.map((item) => {
                    const isActive = location.pathname === item.path ||
                      (item.path !== "/workspace" && item.path !== "/admin" && location.pathname.startsWith(item.path));
                    return (
                      <li key={item.path}>
                        <NavLink
                          to={item.path}
                          className="flex items-center gap-2 px-2 py-1.5 rounded text-xs transition-colors"
                          style={{
                            color: isActive ? "var(--mis-cyan)" : "var(--mis-dim)",
                            background: isActive ? "rgba(34,211,238,0.08)" : "transparent",
                          }}
                          onMouseEnter={(e) => {
                            if (!isActive) (e.currentTarget as HTMLElement).style.color = "var(--mis-text)";
                          }}
                          onMouseLeave={(e) => {
                            if (!isActive) (e.currentTarget as HTMLElement).style.color = "var(--mis-dim)";
                          }}
                        >
                          {item.icon}
                          {item.label}
                        </NavLink>
                      </li>
                    );
                  })}
                </ul>
              )}
            </div>
          );
        })}
      </nav>

      {/* Footer */}
      <div
        className="px-4 py-3 border-t text-[10px]"
        style={{ borderColor: "var(--mis-border)", color: "var(--mis-dim)" }}
      >
        <div>Workspace: AgentOps Demo</div>
        <div style={{ color: "var(--mis-muted)" }}>jiwu@agentops.dev</div>
      </div>
    </aside>
  );
}
