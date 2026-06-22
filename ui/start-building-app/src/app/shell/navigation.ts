import type { LucideIcon } from "lucide-react";
import {
  Activity,
  Bot,
  Boxes,
  Brain,
  CheckSquare,
  ClipboardCheck,
  Database,
  FileCheck2,
  Gauge,
  KeyRound,
  LayoutDashboard,
  ListTree,
  Package,
  Plug,
  ShieldCheck,
  Siren,
  Sparkles,
  Wrench,
} from "lucide-react";
import type { LocaleMode } from "../context/PreferencesContext";

export interface NavigationItem {
  id: string;
  path: string;
  icon: LucideIcon;
  label: { en: string; zh: string };
  keywords?: string[];
}

export interface NavigationGroup {
  id: string;
  label: { en: string; zh: string };
  items: NavigationItem[];
}

export const NAVIGATION: NavigationGroup[] = [
  {
    id: "operate",
    label: { en: "Operate", zh: "运营" },
    items: [
      { id: "mission", path: "/workspace", icon: LayoutDashboard, label: { en: "Mission Control", zh: "任务控制台" }, keywords: ["home", "attention", "首页"] },
      { id: "packages", path: "/work-packages", icon: Boxes, label: { en: "Work Packages", zh: "工作包" }, keywords: ["commander", "project"] },
      { id: "tasks", path: "/tasks", icon: CheckSquare, label: { en: "Tasks", zh: "任务" } },
      { id: "review", path: "/human-review", icon: ClipboardCheck, label: { en: "Human Review", zh: "人工复核" } },
      { id: "deliveries", path: "/deliveries", icon: FileCheck2, label: { en: "Deliveries", zh: "交付" } },
    ],
  },
  {
    id: "workforce",
    label: { en: "Workforce", zh: "员工与运行" },
    items: [
      { id: "agents", path: "/workforce/agents", icon: Bot, label: { en: "Agents", zh: "AI 员工" } },
      { id: "workers", path: "/workforce/workers", icon: Activity, label: { en: "Worker Fleet", zh: "Worker 集群" } },
      { id: "runtimes", path: "/workforce/runtimes", icon: Plug, label: { en: "Runtimes", zh: "运行时" } },
      { id: "gateway", path: "/workforce/gateway", icon: KeyRound, label: { en: "Agent Gateway", zh: "Agent 网关" } },
    ],
  },
  {
    id: "observe",
    label: { en: "Observe", zh: "观测" },
    items: [
      { id: "runs", path: "/observe/runs", icon: ListTree, label: { en: "Runs & Traces", zh: "运行与链路" } },
      { id: "evaluations", path: "/observe/evaluations", icon: Gauge, label: { en: "Evaluations", zh: "评估" } },
      { id: "toolcalls", path: "/observe/tool-calls", icon: Wrench, label: { en: "Tool Calls", zh: "工具调用" } },
      { id: "incidents", path: "/observe/incidents", icon: Siren, label: { en: "Incidents", zh: "故障" } },
    ],
  },
  {
    id: "govern",
    label: { en: "Govern", zh: "治理" },
    items: [
      { id: "approvals", path: "/govern/approvals", icon: ShieldCheck, label: { en: "Security Approvals", zh: "安全审批" } },
      { id: "knowledge", path: "/govern/knowledge", icon: Brain, label: { en: "Knowledge & Memory", zh: "知识与记忆" } },
      { id: "integrations", path: "/govern/integrations", icon: Database, label: { en: "Integrations", zh: "集成" } },
      { id: "templates", path: "/govern/templates", icon: Package, label: { en: "Templates", zh: "模板" } },
      { id: "audit", path: "/govern/audit", icon: ClipboardCheck, label: { en: "Audit", zh: "审计" } },
    ],
  },
  {
    id: "visualize",
    label: { en: "Visualize", zh: "可视化" },
    items: [
      { id: "pixel", path: "/pixel-office", icon: Sparkles, label: { en: "Pixel Office", zh: "像素办公室" } },
    ],
  },
];

export function navLabel(locale: LocaleMode, value: { en: string; zh: string }) {
  return locale === "zh" ? value.zh : value.en;
}

export const FLAT_NAVIGATION = NAVIGATION.flatMap((group) => group.items);
