import { BrowserRouter, Navigate, Route, Routes } from "react-router";
import { AppShell } from "./components/layout/AppShell";
import { AppShellV2 } from "./shell/AppShellV2";
import { WorkspaceHome as LegacyWorkspaceHome } from "./components/pages/WorkspaceHome";
import { PixelOffice } from "./components/pages/PixelOffice";
import { MyTasks } from "./components/pages/MyTasks";
import { AIEmployees } from "./components/pages/AIEmployees";
import { ApprovalsInbox } from "./components/pages/ApprovalsInbox";
import { MemoryLibrary } from "./components/pages/MemoryLibrary";
import { Reports } from "./components/pages/Reports";
import { ControlTower } from "./components/pages/ControlTower";
import { EvaluationRoom } from "./components/pages/EvaluationRoom";
import { AgentDetail } from "./components/pages/AgentDetail";
import { TaskDetail } from "./components/pages/TaskDetail";
import { RunDetail } from "./components/pages/RunDetail";
import { RunLedger } from "./components/pages/RunLedger";
import { ToolCallLedger } from "./components/pages/ToolCallLedger";
import { RuntimeConnectors } from "./components/pages/RuntimeConnectors";
import { NotionBase } from "./components/pages/NotionBase";
import { TemplateSwitching } from "./components/pages/TemplateSwitching";
import { AuditCenter } from "./components/pages/AuditCenter";
import { CustomerProjectReport } from "./components/pages/CustomerProjectReport";
import { MissionControl } from "./modules/mission-control/MissionControl";
import { PreferencesProvider } from "./context/PreferencesContext";

function AppRoutes() {
  return (
    <Routes>
      <Route path="/" element={<Navigate to="/workspace" replace />} />
      <Route path="/workspace" element={<MissionControl />} />
      <Route path="/legacy/workspace" element={<LegacyWorkspaceHome />} />
      <Route path="/workspace/pixel-office" element={<PixelOffice />} />
      <Route path="/workspace/tasks" element={<MyTasks />} />
      <Route path="/workspace/agents" element={<AIEmployees />} />
      <Route path="/workspace/approvals" element={<ApprovalsInbox />} />
      <Route path="/workspace/memory" element={<MemoryLibrary />} />
      <Route path="/workspace/reports" element={<Reports />} />
      <Route path="/workspace/customer-projects/:projectId/report" element={<CustomerProjectReport />} />
      <Route path="/admin" element={<ControlTower />} />
      <Route path="/admin/evaluations" element={<EvaluationRoom />} />
      <Route path="/admin/agents/:id" element={<AgentDetail />} />
      <Route path="/admin/tasks/:id" element={<TaskDetail />} />
      <Route path="/admin/runs" element={<RunLedger />} />
      <Route path="/admin/runs/:id" element={<RunDetail />} />
      <Route path="/admin/toolcalls" element={<ToolCallLedger />} />
      <Route path="/admin/connectors" element={<RuntimeConnectors />} />
      <Route path="/admin/bases/notion" element={<NotionBase />} />
      <Route path="/admin/templates" element={<TemplateSwitching />} />
      <Route path="/admin/audit" element={<AuditCenter />} />

      <Route path="/tasks" element={<MyTasks />} />
      <Route path="/work-packages" element={<Navigate to="/workspace/agents#commander-work-packages" replace />} />
      <Route path="/human-review" element={<Navigate to="/workspace/agents#human-review" replace />} />
      <Route path="/deliveries" element={<Reports />} />
      <Route path="/workforce/agents" element={<AIEmployees />} />
      <Route path="/workforce/workers" element={<AIEmployees />} />
      <Route path="/workforce/runtimes" element={<RuntimeConnectors />} />
      <Route path="/workforce/gateway" element={<AIEmployees />} />
      <Route path="/observe/runs" element={<RunLedger />} />
      <Route path="/observe/evaluations" element={<EvaluationRoom />} />
      <Route path="/observe/tool-calls" element={<ToolCallLedger />} />
      <Route path="/observe/incidents" element={<RunLedger />} />
      <Route path="/govern/approvals" element={<ApprovalsInbox />} />
      <Route path="/govern/knowledge" element={<MemoryLibrary />} />
      <Route path="/govern/integrations" element={<NotionBase />} />
      <Route path="/govern/templates" element={<TemplateSwitching />} />
      <Route path="/govern/audit" element={<AuditCenter />} />
      <Route path="/pixel-office" element={<PixelOffice />} />
    </Routes>
  );
}

function ProductShell() {
  const useV2 = import.meta.env.VITE_UI_V2 !== "false";
  return useV2 ? <AppShellV2><AppRoutes /></AppShellV2> : <AppShell><AppRoutes /></AppShell>;
}

export default function App() {
  return <PreferencesProvider><BrowserRouter><ProductShell /></BrowserRouter></PreferencesProvider>;
}
