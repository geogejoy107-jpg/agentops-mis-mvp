"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { Activity, ClipboardList, Database, ShieldCheck, Workflow } from "lucide-react";

const navItems = [
  { href: "/workspace", label: "Workspace", icon: Activity },
  { href: "/workspace/tasks", label: "Tasks", icon: ClipboardList },
  { href: "/workspace/runs", label: "Runs", icon: Workflow },
  { href: "/workspace/approvals", label: "Approvals", icon: ShieldCheck },
  { href: "/workspace/runs", label: "Ledger", icon: Database },
];

export function AppFrame({ children }: Readonly<{ children: React.ReactNode }>) {
  const pathname = usePathname();

  return (
    <main className="shell">
      <aside className="sidebar">
        <div className="brand">
          <span className="brandMark">A</span>
          <div>
            <strong>AgentOps MIS</strong>
            <span>Next.js parity track</span>
          </div>
        </div>
        <nav className="nav">
          {navItems.map((item) => {
            const Icon = item.icon;
            const active = pathname === item.href;
            return (
              <Link className={`navItem ${active ? "active" : ""}`} href={item.href} key={`${item.href}:${item.label}`}>
                <Icon size={16} />
                {item.label}
              </Link>
            );
          })}
        </nav>
      </aside>
      <section className="content">{children}</section>
    </main>
  );
}
