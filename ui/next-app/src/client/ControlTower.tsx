"use client";

import {
  type FormEvent,
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
} from "react";

import styles from "../../app/control-tower.module.css";
import {
  ControlTowerApiError,
  type ControlTowerSnapshot,
  type HumanSession,
  type TaskDispatchInput,
  createControlTowerClient,
} from "./controlTowerApi";

type SessionPhase = "checking" | "signed-out" | "signed-in";

function displayError(error: unknown) {
  if (error instanceof ControlTowerApiError) return error.message;
  return "控制平面暂时不可用，请稍后重试。";
}

function shortId(value: string | null | undefined) {
  if (!value) return "-";
  return value.length > 22 ? `${value.slice(0, 10)}...${value.slice(-7)}` : value;
}

function dateTime(value: string | null | undefined) {
  if (!value) return "-";
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) return "-";
  return new Intl.DateTimeFormat("zh-CN", {
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
  }).format(parsed);
}

function money(value: number | string | null | undefined) {
  const parsed = Number(value || 0);
  return new Intl.NumberFormat("en-US", {
    style: "currency",
    currency: "USD",
    minimumFractionDigits: parsed > 0 && parsed < 0.01 ? 4 : 2,
    maximumFractionDigits: 6,
  }).format(Number.isFinite(parsed) ? parsed : 0);
}

function percentage(value: number | null | undefined) {
  const normalized = Number(value || 0);
  const percent = normalized <= 1 ? normalized * 100 : normalized;
  return `${Math.round(percent * 10) / 10}%`;
}

function statusClass(status: string) {
  const normalized = status.toLowerCase();
  if (["completed", "approved", "running"].includes(normalized)) {
    return styles.statusPositive;
  }
  if (["failed", "rejected", "blocked", "expired"].includes(normalized)) {
    return styles.statusNegative;
  }
  if (["pending", "waiting_approval", "planned"].includes(normalized)) {
    return styles.statusAttention;
  }
  return styles.statusNeutral;
}

function Status({ value }: { value: string }) {
  return <span className={`${styles.status} ${statusClass(value)}`}>{value}</span>;
}

function EmptyRow({ children, columns }: { children: string; columns: number }) {
  return (
    <tr>
      <td className={styles.emptyRow} colSpan={columns}>{children}</td>
    </tr>
  );
}

export function ControlTower() {
  const api = useMemo(() => createControlTowerClient(), []);
  const [phase, setPhase] = useState<SessionPhase>("checking");
  const [session, setSession] = useState<HumanSession | null>(null);
  const [workspaceId, setWorkspaceId] = useState("");
  const [snapshot, setSnapshot] = useState<ControlTowerSnapshot | null>(null);
  const [authError, setAuthError] = useState("");
  const [dataError, setDataError] = useState("");
  const [authBusy, setAuthBusy] = useState(false);
  const [dataBusy, setDataBusy] = useState(false);
  const [taskBusy, setTaskBusy] = useState(false);
  const [taskMessage, setTaskMessage] = useState("");
  const [taskError, setTaskError] = useState("");
  const [taskReplayKey, setTaskReplayKey] = useState("");
  const [approvalBusyId, setApprovalBusyId] = useState("");
  const [approvalMessage, setApprovalMessage] = useState("");
  const [approvalError, setApprovalError] = useState("");
  const approvalReplayKeys = useRef(new Map<string, string>());
  const [refreshVersion, setRefreshVersion] = useState(0);
  const [lastUpdated, setLastUpdated] = useState<Date | null>(null);

  const applySession = useCallback((next: HumanSession) => {
    setSession(next);
    setWorkspaceId((current) => {
      if (next.memberships.some((item) => item.workspace_id === current)) {
        return current;
      }
      return next.memberships[0]?.workspace_id || "";
    });
    setPhase("signed-in");
    setAuthError("");
  }, []);

  const clearSession = useCallback(() => {
    setSession(null);
    setWorkspaceId("");
    setSnapshot(null);
    setLastUpdated(null);
    setTaskMessage("");
    setTaskError("");
    setTaskReplayKey("");
    setApprovalMessage("");
    setApprovalError("");
    approvalReplayKeys.current.clear();
    setPhase("signed-out");
  }, []);

  useEffect(() => {
    let active = true;
    void api.session()
      .then((current) => {
        if (active) applySession(current);
      })
      .catch((error: unknown) => {
        if (!active) return;
        clearSession();
        if (!(error instanceof ControlTowerApiError && error.status === 401)) {
          setAuthError(displayError(error));
        }
      });
    return () => {
      active = false;
    };
  }, [api, applySession, clearSession]);

  useEffect(() => {
    if (phase !== "signed-in" || !workspaceId) return;
    let active = true;
    setDataBusy(true);
    setDataError("");
    void api.workspaceSnapshot(workspaceId)
      .then((next) => {
        if (!active) return;
        setSnapshot(next);
        setLastUpdated(new Date());
      })
      .catch((error: unknown) => {
        if (!active) return;
        if (error instanceof ControlTowerApiError && error.status === 401) {
          clearSession();
          return;
        }
        setDataError(displayError(error));
      })
      .finally(() => {
        if (active) setDataBusy(false);
      });
    return () => {
      active = false;
    };
  }, [api, clearSession, phase, refreshVersion, workspaceId]);

  async function handleLogin(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    const username = String(form.get("username") || "").trim();
    const password = String(form.get("password") || "");
    setAuthBusy(true);
    setAuthError("");
    try {
      applySession(await api.login(username, password));
    } catch (error) {
      setAuthError(displayError(error));
    } finally {
      setAuthBusy(false);
    }
  }

  async function handleLogout() {
    if (!session) return;
    setAuthBusy(true);
    setAuthError("");
    try {
      await api.logout(session.csrf_token);
      clearSession();
    } catch (error) {
      setAuthError(displayError(error));
    } finally {
      setAuthBusy(false);
    }
  }

  async function handleTaskDispatch(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!session || !workspaceId) return;
    const formElement = event.currentTarget;
    const form = new FormData(formElement);
    const input: TaskDispatchInput = {
      title: String(form.get("title") || "").trim(),
      description: String(form.get("description") || "").trim(),
      owner_agent_id: String(form.get("owner_agent_id") || "").trim(),
      priority: String(form.get("priority") || "medium"),
      risk_level: String(form.get("risk_level") || "medium"),
      acceptance_criteria: String(form.get("acceptance_criteria") || "").trim(),
      budget_limit_usd: Number(form.get("budget_limit_usd") || 0),
    };
    const replayKey = taskReplayKey || `human-task-${crypto.randomUUID()}`;
    setTaskReplayKey(replayKey);
    setTaskBusy(true);
    setTaskError("");
    setTaskMessage("");
    try {
      const receipt = await api.dispatchTask(
        workspaceId,
        session.csrf_token,
        replayKey,
        input,
      );
      formElement.reset();
      setTaskReplayKey("");
      setTaskMessage(`Task ${shortId(receipt.task_id)} 已派发。`);
      setRefreshVersion((value) => value + 1);
    } catch (error) {
      if (error instanceof ControlTowerApiError && error.status === 401) {
        clearSession();
        return;
      }
      setTaskError(displayError(error));
    } finally {
      setTaskBusy(false);
    }
  }

  async function handleApprovalDecision(
    approvalId: string,
    decision: "approve" | "reject",
  ) {
    if (!session || !workspaceId) return;
    const confirmed = window.confirm(
      decision === "approve"
        ? "确认批准这项待审请求？"
        : "确认拒绝这项待审请求？",
    );
    if (!confirmed) return;
    const replayBinding = `${workspaceId}:${approvalId}:${decision}`;
    const replayKey = approvalReplayKeys.current.get(replayBinding)
      || `human-approval-${crypto.randomUUID()}`;
    approvalReplayKeys.current.set(replayBinding, replayKey);
    setApprovalBusyId(approvalId);
    setApprovalError("");
    setApprovalMessage("");
    try {
      await api.decideApproval(
        workspaceId,
        session.csrf_token,
        replayKey,
        approvalId,
        decision,
      );
      approvalReplayKeys.current.delete(replayBinding);
      setApprovalMessage(
        `Approval ${shortId(approvalId)} 已${decision === "approve" ? "批准" : "拒绝"}。`,
      );
      setRefreshVersion((value) => value + 1);
    } catch (error) {
      if (error instanceof ControlTowerApiError && error.status === 401) {
        clearSession();
        return;
      }
      setApprovalError(displayError(error));
    } finally {
      setApprovalBusyId("");
    }
  }

  if (phase === "checking") {
    return (
      <main className={styles.centered} aria-live="polite">
        <div className={styles.brandMark} aria-hidden="true">A</div>
        <p>正在检查会话...</p>
      </main>
    );
  }

  if (phase === "signed-out" || !session) {
    return (
      <main className={styles.loginShell}>
        <header className={styles.loginHeader}>
          <div className={styles.brand}>
            <span className={styles.brandMark} aria-hidden="true">A</span>
            <div>
              <strong>AgentOps MIS</strong>
              <span>Commercial Control Tower</span>
            </div>
          </div>
          <span className={styles.environment}>PostgreSQL</span>
        </header>
        <section className={styles.loginPanel} aria-labelledby="login-title">
          <div>
            <p className={styles.eyebrow}>Human Session</p>
            <h1 id="login-title">登录 Control Tower</h1>
          </div>
          <form className={styles.loginForm} onSubmit={handleLogin}>
            <label>
              用户名
              <input
                autoComplete="username"
                name="username"
                required
                spellCheck={false}
                type="text"
              />
            </label>
            <label>
              密码
              <input
                autoComplete="current-password"
                name="password"
                required
                type="password"
              />
            </label>
            {authError ? <p className={styles.error} role="alert">{authError}</p> : null}
            <button className={styles.primaryButton} disabled={authBusy} type="submit">
              {authBusy ? "登录中..." : "登录"}
            </button>
          </form>
        </section>
      </main>
    );
  }

  const membership = session.memberships.find((item) => item.workspace_id === workspaceId);
  const canDispatchTasks = ["operator", "workspace-admin", "owner"].includes(
    membership?.role || "",
  );
  const canReview = ["approver", "reviewer", "workspace-admin", "owner"].includes(
    membership?.role || "",
  );
  const visibleSnapshot = snapshot?.metrics.workspace_id === workspaceId
    ? snapshot
    : null;
  const metrics = visibleSnapshot?.metrics;
  const taskTotal = metrics?.task_status_distribution.reduce(
    (total, item) => total + Number(item.count || 0),
    0,
  ) ?? 0;
  const failedTasks = metrics?.task_status_distribution
    .filter((item) => ["failed", "blocked"].includes(item.status))
    .reduce((total, item) => total + Number(item.count || 0), 0) ?? 0;
  const loadingValue = dataBusy && !snapshot ? "..." : null;

  return (
    <main className={styles.appShell}>
      <header className={styles.appHeader}>
        <div className={styles.brand}>
          <span className={styles.brandMark} aria-hidden="true">A</span>
          <div>
            <strong>AgentOps MIS</strong>
            <span>Control Tower</span>
          </div>
        </div>
        <div className={styles.headerActions}>
          <span className={styles.liveStatus}>Live</span>
          <button
            className={styles.secondaryButton}
            disabled={dataBusy}
            onClick={() => setRefreshVersion((value) => value + 1)}
            type="button"
          >
            刷新
          </button>
          <button
            className={styles.secondaryButton}
            disabled={authBusy}
            onClick={handleLogout}
            type="button"
          >
            退出
          </button>
        </div>
      </header>

      <section className={styles.identityBand} aria-label="当前身份">
        <div>
          <span className={styles.fieldLabel}>Human</span>
          <strong>{session.user.name}</strong>
          <code>{shortId(session.user.user_id)}</code>
        </div>
        <label>
          <span className={styles.fieldLabel}>Workspace</span>
          <select
            value={workspaceId}
            onChange={(event) => {
              setWorkspaceId(event.target.value);
              setTaskReplayKey("");
              setTaskMessage("");
              setTaskError("");
              setApprovalMessage("");
              setApprovalError("");
              approvalReplayKeys.current.clear();
            }}
          >
            {session.memberships.map((item) => (
              <option key={item.workspace_id} value={item.workspace_id}>
                {item.workspace_id}
              </option>
            ))}
          </select>
        </label>
        <div>
          <span className={styles.fieldLabel}>Role</span>
          <strong>{membership?.role || "-"}</strong>
        </div>
        <div>
          <span className={styles.fieldLabel}>Updated</span>
          <strong>{visibleSnapshot && lastUpdated ? dateTime(lastUpdated.toISOString()) : "-"}</strong>
        </div>
      </section>

      {authError ? <p className={styles.errorBanner} role="alert">{authError}</p> : null}
      {dataError ? <p className={styles.errorBanner} role="alert">{dataError}</p> : null}

      <section className={styles.metrics} aria-label="Workspace metrics">
        <div>
          <span>Agents</span>
          <strong>{loadingValue ?? metrics?.agents_running ?? 0}<small> / {loadingValue ?? metrics?.agents_total ?? 0}</small></strong>
          <small>running</small>
        </div>
        <div>
          <span>Tasks</span>
          <strong>{loadingValue ?? metrics?.tasks_completed_total ?? 0}<small> / {loadingValue ?? taskTotal}</small></strong>
          <small>completed</small>
        </div>
        <div>
          <span>Pending approvals</span>
          <strong>{loadingValue ?? metrics?.pending_approvals ?? 0}</strong>
          <small>awaiting Human review</small>
        </div>
        <div>
          <span>Total cost</span>
          <strong>{loadingValue ?? money(metrics?.total_cost_usd)}</strong>
          <small>workspace lifetime</small>
        </div>
        <div>
          <span>Failure rate</span>
          <strong>{loadingValue ?? percentage(metrics?.failure_rate)}</strong>
          <small>{loadingValue ?? failedTasks} failed tasks</small>
        </div>
      </section>

      <section className={styles.workspaceSection} aria-labelledby="dispatch-heading">
        <div className={styles.sectionHeading}>
          <div>
            <p className={styles.eyebrow}>Human dispatch</p>
            <h2 id="dispatch-heading">Create Task</h2>
          </div>
          <span>{visibleSnapshot?.agents.length ?? 0} workspace agents</span>
        </div>
        <form
          className={styles.taskForm}
          key={workspaceId}
          onChange={() => setTaskReplayKey("")}
          onSubmit={handleTaskDispatch}
        >
          <label className={styles.taskTitleField}>
            <span>Title</span>
            <input maxLength={160} name="title" required type="text" />
          </label>
          <label>
            <span>Agent</span>
            <select
              disabled={!canDispatchTasks || !(visibleSnapshot?.agents.length)}
              name="owner_agent_id"
              required
            >
              <option value="">选择 Agent</option>
              {visibleSnapshot?.agents.map((agent) => (
                <option
                  disabled={agent.status === "disabled"}
                  key={agent.agent_id}
                  value={agent.agent_id}
                >
                  {agent.name} · {agent.runtime_type} · {agent.status}
                </option>
              ))}
            </select>
          </label>
          <label>
            <span>Priority</span>
            <select defaultValue="medium" name="priority">
              <option value="low">Low</option>
              <option value="medium">Medium</option>
              <option value="high">High</option>
              <option value="urgent">Urgent</option>
            </select>
          </label>
          <label>
            <span>Risk</span>
            <select defaultValue="medium" name="risk_level">
              <option value="low">Low</option>
              <option value="medium">Medium</option>
              <option value="high">High</option>
              <option value="critical">Critical</option>
            </select>
          </label>
          <label>
            <span>Budget USD</span>
            <input
              defaultValue="0"
              max="1000000"
              min="0"
              name="budget_limit_usd"
              step="0.01"
              type="number"
            />
          </label>
          <label className={styles.taskWideField}>
            <span>Description</span>
            <textarea maxLength={1200} name="description" rows={3} />
          </label>
          <label className={styles.taskWideField}>
            <span>Acceptance criteria</span>
            <textarea maxLength={600} name="acceptance_criteria" rows={3} />
          </label>
          <div className={styles.formActions}>
            <button
              className={styles.primaryButton}
              disabled={
                taskBusy
                || !canDispatchTasks
                || !(visibleSnapshot?.agents.length)
              }
              type="submit"
            >
              {taskBusy ? "派发中..." : "创建并派发"}
            </button>
            {!canDispatchTasks ? (
              <span>需要 operator、workspace-admin 或 owner 权限。</span>
            ) : !visibleSnapshot?.agents.length ? (
              <span>当前 workspace 没有可派发 Agent。</span>
            ) : null}
          </div>
        </form>
        {taskMessage ? <p className={styles.successBanner} role="status">{taskMessage}</p> : null}
        {taskError ? <p className={styles.errorBanner} role="alert">{taskError}</p> : null}
      </section>

      <section className={styles.workspaceSection} aria-labelledby="tasks-heading">
        <div className={styles.sectionHeading}>
          <div>
            <p className={styles.eyebrow}>Workspace ledger</p>
            <h2 id="tasks-heading">Tasks</h2>
          </div>
          <span>{visibleSnapshot?.tasks.length ?? 0} recent</span>
        </div>
        <div className={styles.tableScroll}>
          <table>
            <thead>
              <tr><th>Task</th><th>Status</th><th>Priority</th><th>Risk</th><th>Owner Agent</th><th>Updated</th></tr>
            </thead>
            <tbody>
              {visibleSnapshot?.tasks.map((task) => (
                <tr key={task.task_id}>
                  <td><strong>{task.title}</strong><code>{shortId(task.task_id)}</code></td>
                  <td><Status value={task.status} /></td>
                  <td>{task.priority}</td>
                  <td>{task.risk_level}</td>
                  <td><code>{shortId(task.owner_agent_id)}</code></td>
                  <td>{dateTime(task.updated_at)}</td>
                </tr>
              ))}
              {!visibleSnapshot?.tasks.length ? (
                <EmptyRow columns={6}>{dataBusy ? "正在加载 Tasks..." : "暂无 Task"}</EmptyRow>
              ) : null}
            </tbody>
          </table>
        </div>
      </section>

      <section className={styles.workspaceSection} aria-labelledby="runs-heading">
        <div className={styles.sectionHeading}>
          <div>
            <p className={styles.eyebrow}>Execution</p>
            <h2 id="runs-heading">Runs</h2>
          </div>
          <span>{visibleSnapshot?.runs.length ?? 0} recent</span>
        </div>
        <div className={styles.tableScroll}>
          <table>
            <thead>
              <tr><th>Run</th><th>Status</th><th>Runtime</th><th>Agent</th><th>Cost</th><th>Started</th></tr>
            </thead>
            <tbody>
              {visibleSnapshot?.runs.map((run) => (
                <tr key={run.run_id}>
                  <td><strong>{shortId(run.run_id)}</strong><code>{shortId(run.task_id)}</code></td>
                  <td><Status value={run.status} /></td>
                  <td>{run.runtime_type}</td>
                  <td><code>{shortId(run.agent_id)}</code></td>
                  <td>{money(run.cost_usd_exact || run.cost_usd)}</td>
                  <td>{dateTime(run.started_at)}</td>
                </tr>
              ))}
              {!visibleSnapshot?.runs.length ? (
                <EmptyRow columns={6}>{dataBusy ? "正在加载 Runs..." : "暂无 Run"}</EmptyRow>
              ) : null}
            </tbody>
          </table>
        </div>
      </section>

      <section className={styles.workspaceSection} aria-labelledby="approvals-heading">
        <div className={styles.sectionHeading}>
          <div>
            <p className={styles.eyebrow}>Human review queue</p>
            <h2 id="approvals-heading">Approvals</h2>
          </div>
          <span>{visibleSnapshot?.approvals.filter((item) => item.decision === "pending").length ?? 0} pending</span>
        </div>
        {approvalMessage ? (
          <p className={styles.successBanner} role="status">{approvalMessage}</p>
        ) : null}
        {approvalError ? (
          <p className={styles.errorBanner} role="alert">{approvalError}</p>
        ) : null}
        <div className={styles.tableScroll}>
          <table>
            <thead>
              <tr><th>Approval</th><th>Decision</th><th>Kind</th><th>Run</th><th>Agent</th><th>Requested</th><th>Actions</th></tr>
            </thead>
            <tbody>
              {visibleSnapshot?.approvals.map((approval) => (
                <tr key={approval.approval_id}>
                  <td><strong>{shortId(approval.approval_id)}</strong><code>{shortId(approval.task_id)}</code></td>
                  <td><Status value={approval.decision} /></td>
                  <td>{approval.approval_kind.replaceAll("_", " ")}</td>
                  <td><code>{shortId(approval.run_id)}</code></td>
                  <td><code>{shortId(approval.requested_by_agent_id)}</code></td>
                  <td>{dateTime(approval.created_at)}</td>
                  <td>
                    {approval.decision === "pending" ? (
                      <div className={styles.rowActions}>
                        <button
                          className={styles.approveButton}
                          disabled={!canReview || approvalBusyId === approval.approval_id}
                          onClick={() => handleApprovalDecision(approval.approval_id, "approve")}
                          type="button"
                        >
                          批准
                        </button>
                        <button
                          className={styles.rejectButton}
                          disabled={!canReview || approvalBusyId === approval.approval_id}
                          onClick={() => handleApprovalDecision(approval.approval_id, "reject")}
                          type="button"
                        >
                          拒绝
                        </button>
                      </div>
                    ) : "-"}
                  </td>
                </tr>
              ))}
              {!visibleSnapshot?.approvals.length ? (
                <EmptyRow columns={7}>{dataBusy ? "正在加载 Approvals..." : "暂无 Approval"}</EmptyRow>
              ) : null}
            </tbody>
          </table>
        </div>
      </section>
    </main>
  );
}
