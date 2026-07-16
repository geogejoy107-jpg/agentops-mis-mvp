import { BrowserRouter, Routes, Route, Navigate, useParams } from "react-router";
import { AppShell } from "./components/layout/AppShell";
import { WorkspaceHome } from "./components/pages/WorkspaceHome";
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
import { PreferencesProvider } from "./context/PreferencesContext";

function LegacyTaskDetailRedirect() {
  const { id = "" } = useParams();
  return <Navigate to={`/workspace/tasks/${encodeURIComponent(id)}`} replace />;
}

function LegacyRunDetailRedirect() {
  const { id = "" } = useParams();
  return <Navigate to={`/workspace/runs/${encodeURIComponent(id)}`} replace />;
}

function LegacyAgentDetailRedirect() {
  const { id = "" } = useParams();
  return <Navigate to={`/workspace/agents/${encodeURIComponent(id)}`} replace />;
}

export default function App() {
  return (
    <PreferencesProvider>
      <BrowserRouter>
        <AppShell>
          <Routes>
            <Route path="/" element={<Navigate to="/workspace" replace />} />
            <Route path="/workspace" element={<WorkspaceHome />} />
            <Route path="/workspace/pixel-office" element={<PixelOffice />} />
            <Route path="/workspace/tasks" element={<MyTasks />} />
            <Route path="/workspace/tasks/:id" element={<TaskDetail />} />
            <Route path="/workspace/agents" element={<AIEmployees />} />
            <Route path="/workspace/agents/:id" element={<AgentDetail />} />
            <Route path="/workspace/approvals" element={<ApprovalsInbox />} />
            <Route path="/workspace/memory" element={<MemoryLibrary />} />
            <Route path="/workspace/reports" element={<Reports />} />
            <Route path="/workspace/runs" element={<RunLedger />} />
            <Route path="/workspace/runs/:id" element={<RunDetail />} />
            <Route path="/workspace/customer-projects/:projectId/report" element={<CustomerProjectReport />} />
            <Route path="/workspace/evaluations" element={<EvaluationRoom />} />
            <Route path="/workspace/tool-calls" element={<ToolCallLedger />} />
            <Route path="/workspace/connectors" element={<RuntimeConnectors />} />
            <Route path="/workspace/external-bases/notion" element={<NotionBase />} />
            <Route path="/workspace/templates" element={<TemplateSwitching />} />
            <Route path="/workspace/audit" element={<AuditCenter />} />
            <Route path="/admin" element={<ControlTower />} />
            <Route path="/admin/evaluations" element={<Navigate to="/workspace/evaluations" replace />} />
            <Route path="/admin/agents/:id" element={<LegacyAgentDetailRedirect />} />
            <Route path="/admin/tasks/:id" element={<LegacyTaskDetailRedirect />} />
            <Route path="/admin/runs" element={<Navigate to="/workspace/runs" replace />} />
            <Route path="/admin/runs/:id" element={<LegacyRunDetailRedirect />} />
            <Route path="/admin/toolcalls" element={<Navigate to="/workspace/tool-calls" replace />} />
            <Route path="/admin/connectors" element={<Navigate to="/workspace/connectors" replace />} />
            <Route path="/admin/bases/notion" element={<Navigate to="/workspace/external-bases/notion" replace />} />
            <Route path="/admin/templates" element={<Navigate to="/workspace/templates" replace />} />
            <Route path="/admin/audit" element={<Navigate to="/workspace/audit" replace />} />
          </Routes>
        </AppShell>
      </BrowserRouter>
    </PreferencesProvider>
  );
}
