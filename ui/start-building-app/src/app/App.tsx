import { BrowserRouter, Routes, Route, Navigate } from "react-router";
import { AppShell } from "./components/layout/AppShell";
import { WorkspaceHome } from "./components/pages/WorkspaceHome";
import { MyTasks } from "./components/pages/MyTasks";
import { AIEmployees } from "./components/pages/AIEmployees";
import { ApprovalsInbox } from "./components/pages/ApprovalsInbox";
import { MemoryLibrary } from "./components/pages/MemoryLibrary";
import { Reports } from "./components/pages/Reports";
import { ControlTower } from "./components/pages/ControlTower";
import { AgentDetail } from "./components/pages/AgentDetail";
import { TaskDetail } from "./components/pages/TaskDetail";
import { RunDetail } from "./components/pages/RunDetail";
import { RunLedger } from "./components/pages/RunLedger";
import { ToolCallLedger } from "./components/pages/ToolCallLedger";
import { RuntimeConnectors } from "./components/pages/RuntimeConnectors";
import { NotionBase } from "./components/pages/NotionBase";
import { TemplateSwitching } from "./components/pages/TemplateSwitching";
import { AuditCenter } from "./components/pages/AuditCenter";

export default function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route element={<AppShell />}>
          <Route index element={<Navigate to="/workspace" replace />} />
          {/* Client Workspace */}
          <Route path="/workspace" element={<WorkspaceHome />} />
          <Route path="/workspace/tasks" element={<MyTasks />} />
          <Route path="/workspace/agents" element={<AIEmployees />} />
          <Route path="/workspace/approvals" element={<ApprovalsInbox />} />
          <Route path="/workspace/memory" element={<MemoryLibrary />} />
          <Route path="/workspace/reports" element={<Reports />} />
          {/* Admin Console */}
          <Route path="/admin" element={<ControlTower />} />
          <Route path="/admin/agents/:id" element={<AgentDetail />} />
          <Route path="/admin/tasks/:id" element={<TaskDetail />} />
          <Route path="/admin/runs" element={<RunLedger />} />
          <Route path="/admin/runs/:id" element={<RunDetail />} />
          <Route path="/admin/toolcalls" element={<ToolCallLedger />} />
          <Route path="/admin/connectors" element={<RuntimeConnectors />} />
          <Route path="/admin/bases/notion" element={<NotionBase />} />
          <Route path="/admin/templates" element={<TemplateSwitching />} />
          <Route path="/admin/audit" element={<AuditCenter />} />
          <Route path="*" element={<Navigate to="/workspace" replace />} />
        </Route>
      </Routes>
    </BrowserRouter>
  );
}
