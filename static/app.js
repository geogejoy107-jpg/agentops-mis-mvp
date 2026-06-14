const routes = [
  ['dashboard','Dashboard','overview'], ['agents','Agents','registry'], ['tasks','Tasks','ledger'],
  ['runs','Runs','ledger'], ['tool-calls','Tool Calls','tools'], ['approvals','Approvals','HITL'],
  ['memory','Memory','governance'], ['evaluations','Evaluations','quality'], ['audit','Audit','trace'],
  ['integrations','Integrations','runtime'], ['workflows','AI Workflows','real work'], ['settings','Settings','config']
];
const app = document.getElementById('app');
const pageTitle = document.getElementById('page-title');
const pageSubtitle = document.getElementById('page-subtitle');
const nav = document.getElementById('nav');
const refreshBtn = document.getElementById('refresh-btn');

function routeName(){ return location.pathname.replace(/^\//,'') || 'dashboard'; }
function setRoute(r){ history.pushState({}, '', '/' + r); render(); }
function statusBadge(s){
  const cls = ['completed','approved','idle','pass','ready','configured'].includes(s) ? 'ok' : ['waiting_approval','pending','running','candidate','dry_run_only','missing_config'].includes(s) ? 'warn' : ['failed','blocked','rejected','critical','high','error','unavailable','not_configured'].includes(s) ? 'danger' : 'info';
  return `<span class="badge ${cls}">${escapeHtml(s ?? '')}</span>`;
}
function riskBadge(s){ return statusBadge(s); }
function escapeHtml(v){ return String(v ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#039;'}[c])); }
function fmt(v){ if(v === null || v === undefined || v === '') return '<span class="muted">—</span>'; return escapeHtml(v); }
function money(v){ return '$' + Number(v || 0).toFixed(3); }
function toast(msg){ const el=document.createElement('div'); el.className='toast'; el.textContent=msg; document.body.appendChild(el); setTimeout(()=>el.remove(),2800); }
async function api(path, opts={}){
  const res = await fetch(path, {headers:{'Content-Type':'application/json'}, ...opts});
  if(!res.ok) throw new Error((await res.text()) || res.statusText);
  return res.json();
}
function renderNav(){
  const current = routeName().split('/')[0];
  nav.innerHTML = routes.map(([r,label,k]) => `<a href="/${r}" class="nav-item ${current===r?'active':''}" onclick="event.preventDefault(); setRoute('${r}')"><span>${label}</span><small>${k}</small></a>`).join('');
}
function table(rows, cols){
  return `<div class="table-wrap"><table><thead><tr>${cols.map(c=>`<th>${escapeHtml(c.label)}</th>`).join('')}</tr></thead><tbody>${rows.map(row=>`<tr>${cols.map(c=>`<td>${c.render?c.render(row):fmt(row[c.key])}</td>`).join('')}</tr>`).join('')}</tbody></table></div>`;
}
function formData(form){ return Object.fromEntries(new FormData(form).entries()); }
function setTitle(title, subtitle){ pageTitle.textContent=title; pageSubtitle.textContent=subtitle; }

async function renderDashboard(){
  setTitle('Dashboard','Management cockpit for agents, tasks, approvals, memory and run ledger.');
  const m = await api('/api/dashboard/metrics');
  app.innerHTML = `
  <div class="grid">
    ${metric('总 Agent 数', m.agents_total, 'registry')}
    ${metric('运行中 Agent', m.agents_running, 'status')}
    ${metric('本周/累计完成', m.tasks_completed_total, 'tasks')}
    ${metric('总成本', money(m.total_cost_usd), 'token/tool')}
    ${metric('平均任务成本', money(m.avg_task_cost_usd), 'completed runs')}
    ${metric('失败率', Math.round(m.failure_rate*100)+'%', 'blocked/failed tasks')}
    ${metric('待审批', m.pending_approvals, 'HITL queue')}
    ${metric('过期/待复核记忆', m.stale_or_due_memories, 'TTL/review')}
  </div>
  <div class="grid-2 section">
    <div class="card"><h3>任务状态分布</h3>${table(m.task_status_distribution,[{key:'status',label:'Status',render:r=>statusBadge(r.status)},{key:'count',label:'Count'}])}</div>
    <div class="card"><h3>Top 5 Cost Agents</h3>${table(m.top_cost_agents,[{key:'name',label:'Agent'},{key:'cost_usd',label:'Cost',render:r=>money(r.cost_usd)}])}</div>
  </div>
  <div class="grid-2 section">
    <div class="card"><h3>Top 5 Failing Agents</h3>${table(m.top_failing_agents,[{key:'name',label:'Agent'},{key:'failures',label:'Failures'}])}</div>
    <div class="card"><h3>最近 20 条 Run Ledger</h3>${runTable(m.recent_runs)}</div>
  </div>
  <div class="grid-2 section">
    <div class="card"><h3>Runtime Health</h3>${runtimeTable(m.runtime_health || [])}</div>
    <div class="card"><h3>OpenClaw Cron Health</h3>${table([m.openclaw_import || {}],[{key:'agents',label:'Agents'},{key:'cron_tasks',label:'Cron Tasks'},{key:'enabled_cron_tasks',label:'Enabled'},{key:'cron_runs',label:'Runs'},{key:'failed_runs',label:'Failures'},{key:'failed_quality_gates',label:'Failed Gates'}])}</div>
  </div>
  <div class="section card">
    <h3>Agent Performance Summary</h3>${performanceTable(m.agent_performance_summary || [])}
  </div>`;
}
function metric(label, value, sub){ return `<div class="card"><div class="muted">${label}</div><div class="metric">${value}</div><div class="muted">${sub}</div></div>`; }
function runTable(rows){ return table(rows,[{key:'run_id',label:'Run',render:r=>`<a onclick="setRoute('runs/${r.run_id}')">${r.run_id}</a>`},{key:'status',label:'Status',render:r=>statusBadge(r.status)},{key:'agent_id',label:'Agent'},{key:'cost_usd',label:'Cost',render:r=>money(r.cost_usd)}]); }
function runtimeTable(rows){ return table(rows,[{key:'provider',label:'Provider'},{key:'status',label:'Status',render:r=>statusBadge(r.status)},{key:'details',label:'Details',render:r=>`<code>${escapeHtml(JSON.stringify(Object.fromEntries(Object.entries(r).filter(([k])=>!['provider','status'].includes(k)))))}</code>`}]); }
function performanceTable(rows){ return table(rows,[{key:'name',label:'Agent',render:r=>`<a onclick="setRoute('agents/${r.agent_id}')">${escapeHtml(r.name)}</a><br><span class="muted">${escapeHtml(r.runtime_type)}</span>`},{key:'total_runs',label:'Runs'},{key:'success_rate',label:'Success',render:r=>Math.round(Number(r.success_rate||0)*100)+'%'},{key:'avg_duration_ms',label:'Avg ms'},{key:'failures',label:'Failures'},{key:'approval_required_count',label:'Approvals'}]); }

async function renderAgents(){
  setTitle('Agent Registry','Digital employee identity, runtime, tools, budgets and performance.');
  const agents = await api('/api/agents');
  app.innerHTML = `<div class="grid-2"><div class="card"><h3>创建 Agent</h3><form id="agent-form" class="form">
    <div class="form-row"><label>Name<input name="name" value="New Research Agent"/></label><label>Role<input name="role" value="Researcher"/></label></div>
    <label>Description<textarea name="description">Searches sources and proposes memory candidates.</textarea></label>
    <div class="form-row"><label>Runtime<select name="runtime_type"><option>mock</option><option>claude_code</option><option>codex</option><option>openhands</option><option>crewai</option><option>langgraph</option><option>openclaw</option><option>hermes</option></select></label><label>Budget USD<input name="budget_limit_usd" type="number" step="0.01" value="5"/></label></div>
    <button>创建</button></form></div><div class="card"><h3>Agent 列表</h3>${agentTable(agents)}</div></div>`;
  document.getElementById('agent-form').onsubmit = async e => { e.preventDefault(); const d=formData(e.target); await api('/api/agents',{method:'POST',body:JSON.stringify({...d,allowed_tools:['browser.search','github.read','memory.propose']})}); toast('Agent created'); render(); };
}
function agentTable(agents){ return table(agents,[{key:'name',label:'Name',render:r=>`<a onclick="setRoute('agents/${r.agent_id}')"><b>${escapeHtml(r.name)}</b></a><br><span class="muted">${r.role}</span>`},{key:'runtime_type',label:'Runtime'},{key:'status',label:'Status',render:r=>statusBadge(r.status)},{key:'budget_limit_usd',label:'Budget',render:r=>money(r.budget_limit_usd)},{key:'allowed_tools',label:'Tools',render:r=>`<code>${escapeHtml(r.allowed_tools)}</code>`}]); }
async function renderAgentDetail(id){
  const data = await api('/api/agents/'+id); const perf = await api(`/api/agents/${id}/performance`); const a=data.agent;
  setTitle(a.name, 'Agent detail: tasks, runs, permissions and cost.');
  app.innerHTML = `<div class="grid">
    ${metric('Total Runs', perf.total_runs, 'agent ledger')}
    ${metric('Success Rate', Math.round(perf.success_rate*100)+'%', 'completed / total')}
    ${metric('Avg Duration', perf.avg_duration_ms+'ms', 'runtime latency')}
    ${metric('Total Cost', money(perf.total_cost_usd), 'recorded spend')}
    ${metric('Failures', perf.failures, 'failed/blocked')}
    ${metric('Approvals', perf.approval_required_count, 'approval-required runs')}
  </div>
  <div class="grid-3 section"><div class="card"><h3>Profile</h3><pre>${escapeHtml(JSON.stringify(a,null,2))}</pre></div><div class="card"><h3>Tasks</h3>${taskMiniTable(data.tasks)}</div><div class="card"><h3>Recent Errors</h3>${table(perf.recent_error_types,[{key:'error_type',label:'Error Type'},{key:'count',label:'Count'}])}</div></div>
  <div class="section card"><h3>Runs</h3>${runTable(perf.recent_runs)}</div>`;
}

async function renderTasks(){
  setTitle('Task Management','Task ledger, assignment, status board and acceptance criteria.');
  const tasks = await api('/api/tasks'); const agents = await api('/api/agents');
  const statuses = ['backlog','planned','running','waiting_approval','blocked','completed','failed','canceled'];
  app.innerHTML = `<div class="grid-2"><div class="card"><h3>创建任务</h3><form id="task-form" class="form">
    <label>Title<input name="title" value="调研一个新 Agent-MIS 竞品"/></label>
    <label>Description<textarea name="description">Use GitHub, HN and issue discussions; produce sourced summary.</textarea></label>
    <div class="form-row"><label>Owner Agent<select name="owner_agent_id">${agents.map(a=>`<option value="${a.agent_id}">${a.name}</option>`).join('')}</select></label><label>Risk<select name="risk_level"><option>low</option><option selected>medium</option><option>high</option><option>critical</option></select></label></div>
    <div class="form-row"><label>Budget USD<input name="budget_limit_usd" type="number" step="0.01" value="3"/></label><label>Priority<select name="priority"><option>low</option><option selected>medium</option><option>high</option></select></label></div>
    <label>Acceptance Criteria<textarea name="acceptance_criteria">Must include sources, issues, risks, and MVP implications.</textarea></label>
    <button>创建任务</button></form></div><div class="card"><h3>任务表</h3>${taskMiniTable(tasks)}</div></div>
    <div class="section kanban">${statuses.map(st=>`<div class="column"><h4>${st}</h4>${tasks.filter(t=>t.status===st).map(t=>`<div class="task-card"><b><a onclick="setRoute('tasks/${t.task_id}')">${escapeHtml(t.title)}</a></b>${statusBadge(t.risk_level)}<p class="muted">${escapeHtml(t.owner_agent_id)}</p></div>`).join('') || '<p class="muted">No tasks</p>'}</div>`).join('')}</div>`;
  document.getElementById('task-form').onsubmit = async e => { e.preventDefault(); await api('/api/tasks',{method:'POST',body:JSON.stringify(formData(e.target))}); toast('Task created'); render(); };
}
function taskMiniTable(rows){ return table(rows,[{key:'title',label:'Task',render:r=>`<a onclick="setRoute('tasks/${r.task_id}')"><b>${escapeHtml(r.title)}</b></a><br><span class="muted">${r.task_id}</span>`},{key:'status',label:'Status',render:r=>statusBadge(r.status)},{key:'risk_level',label:'Risk',render:r=>riskBadge(r.risk_level)},{key:'owner_agent_id',label:'Owner'},{key:'budget_limit_usd',label:'Budget',render:r=>money(r.budget_limit_usd)}]); }
async function renderTaskDetail(id){
  const data = await api('/api/tasks/'+id); const t=data.task;
  setTitle(t.title, 'Task detail: runs, artifacts, approvals, cost, evaluation and memory.');
  app.innerHTML = `<div class="actions"><button onclick="startRun('${t.task_id}','${t.owner_agent_id}')">Start mock run</button><button onclick="patchStatus('${t.task_id}','completed')">Mark completed</button><button onclick="patchStatus('${t.task_id}','blocked')">Block</button></div>
  <div class="grid-2 section"><div class="card"><h3>Task</h3><pre>${escapeHtml(JSON.stringify(t,null,2))}</pre></div><div class="card"><h3>Runs</h3>${runTable(data.runs)}</div></div>
  <div class="grid-2 section"><div class="card"><h3>Approvals</h3>${approvalTable(data.approvals)}</div><div class="card"><h3>Evaluations</h3>${evaluationTable(data.evaluations)}</div></div>
  <div class="grid-2 section"><div class="card"><h3>Memory</h3>${memoryTable(data.memories)}</div><div class="card"><h3>Artifacts</h3>${table(data.artifacts,[{key:'title',label:'Title'},{key:'artifact_type',label:'Type'},{key:'summary',label:'Summary'}])}</div></div>`;
}
async function patchStatus(taskId,status){ await api(`/api/tasks/${taskId}/status`,{method:'PATCH',body:JSON.stringify({status})}); toast('Task updated'); render(); }
async function startRun(taskId,agentId){ const r=await api('/api/mock-runs/start',{method:'POST',body:JSON.stringify({task_id:taskId,agent_id:agentId})}); toast(r.approval_required ? 'Run waiting approval' : 'Run completed'); setRoute('runs/'+r.run_id); }

async function renderRuns(){ setTitle('Run Ledger','Immutable-like execution records: task, agent, model, cost, errors and delegation.'); const rows=await api('/api/runs'); app.innerHTML=`<div class="card">${runTable(rows)}</div>`; }
async function renderRunDetail(id){ const d=await api('/api/runs/'+id); const graph=await api(`/api/runs/${id}/graph`); const r=d.run; setTitle(r.run_id,'Run detail: tool calls, approvals, evaluations and delegation graph.'); app.innerHTML=`<div class="actions"><button onclick="completeRun('${r.run_id}')">Force complete</button><button onclick="runRuleCheck('${r.run_id}')">Run rule check</button></div>
<div class="grid-2 section"><div class="card"><h3>Run</h3><pre>${escapeHtml(JSON.stringify(r,null,2))}</pre></div><div class="card"><h3>Parent / Delegation</h3>${table([{parent_run_id:r.parent_run_id,delegation_id:r.delegation_id,children:(graph.children||[]).length,siblings:(graph.siblings_by_delegation||[]).length}],[{key:'parent_run_id',label:'Parent'},{key:'delegation_id',label:'Delegation'},{key:'children',label:'Child Runs'},{key:'siblings',label:'Sibling Runs'}])}</div></div>
<div class="grid-2 section"><div class="card"><h3>Child Runs</h3>${runTable(graph.children||[])}</div><div class="card"><h3>Sibling Runs</h3>${runTable(graph.siblings_by_delegation||[])}</div></div>
<div class="grid-2 section"><div class="card"><h3>Tool Calls</h3>${toolCallTable(d.tool_calls)}</div><div class="card"><h3>Evaluations</h3>${evaluationTable(d.evaluations)}</div></div>
<div class="grid-2 section"><div class="card"><h3>Approvals</h3>${approvalTable(d.approvals)}</div><div class="card"><h3>Artifacts</h3>${table(d.artifacts||[],[{key:'title',label:'Title'},{key:'artifact_type',label:'Type'},{key:'summary',label:'Summary'}])}</div></div>`; }
async function completeRun(id){ await api(`/api/mock-runs/${id}/complete`,{method:'POST',body:'{}'}); toast('Run completion attempted'); render(); }
async function runRuleCheck(id){ await api('/api/evaluations/run-rule-check',{method:'POST',body:JSON.stringify({run_id:id})}); toast('Rule evaluation created'); render(); }

async function renderToolCalls(){ setTitle('Tool Call Ledger','Tool calls, normalized arguments, risk, target resources and side effects.'); const rows=await api('/api/tool-calls'); app.innerHTML=`<div class="card">${toolCallTable(rows)}</div>`; }
function toolCallTable(rows){ return table(rows,[{key:'tool_call_id',label:'Tool Call'},{key:'tool_name',label:'Tool'},{key:'tool_category',label:'Category'},{key:'risk_level',label:'Risk',render:r=>riskBadge(r.risk_level)},{key:'status',label:'Status',render:r=>statusBadge(r.status)},{key:'target_resource',label:'Target'},{key:'action',label:'Action',render:r=>r.risk_level==='high'||r.risk_level==='critical'?`<button onclick="requestApproval('${r.tool_call_id}')">Request approval</button>`:''}]); }
async function requestApproval(tcId){ await api(`/api/tool-calls/${tcId}/request-approval`,{method:'POST',body:'{}'}); toast('Approval requested'); setRoute('approvals'); }

async function renderApprovals(){ setTitle('Approval Workflow','Human-in-the-loop queue for high-risk tool calls.'); const rows=await api('/api/approvals'); app.innerHTML=`<div class="card">${approvalTable(rows)}</div>`; }
function approvalTable(rows){ return table(rows,[{key:'approval_id',label:'Approval'},{key:'decision',label:'Decision',render:r=>statusBadge(r.decision)},{key:'tool_call_id',label:'Tool Call'},{key:'requested_by_agent_id',label:'Agent'},{key:'reason',label:'Reason'},{key:'action',label:'Action',render:r=>r.decision==='pending'?`<div class="actions"><button class="ok" onclick="decideApproval('${r.approval_id}','approve')">Approve</button><button class="danger" onclick="decideApproval('${r.approval_id}','reject')">Reject</button></div>`:''}]); }
async function decideApproval(id,decision){ await api(`/api/approvals/${id}/${decision}`,{method:'POST',body:'{}'}); toast('Approval '+decision); render(); }

async function renderMemory(){ setTitle('Organizational Memory','Structured memory with scope, evidence, confidence, TTL and review queue.'); const rows=await api('/api/memories'); app.innerHTML=`<div class="card">${memoryTable(rows)}</div>`; }
function memoryTable(rows){ return table(rows,[{key:'memory_type',label:'Type',render:r=>`${statusBadge(r.scope)} ${escapeHtml(r.memory_type)}`},{key:'canonical_text',label:'Canonical Text'},{key:'confidence',label:'Confidence'},{key:'review_status',label:'Review',render:r=>statusBadge(r.review_status)},{key:'source_ref',label:'Source'},{key:'ttl_review_due_at',label:'TTL'},{key:'action',label:'Action',render:r=>r.review_status==='candidate'?`<div class="actions"><button class="ok" onclick="reviewMemory('${r.memory_id}','approve')">Approve</button><button class="danger" onclick="reviewMemory('${r.memory_id}','reject')">Reject</button></div>`:''}]); }
async function reviewMemory(id,decision){ await api(`/api/memories/${id}/${decision}`,{method:'POST',body:'{}'}); toast('Memory '+decision); render(); }

async function renderEvaluations(){ setTitle('Evaluation / Quality Gate','Rule, human and mock LLM evaluations, quality gates and performance signals.'); const rows=await api('/api/evaluations'); app.innerHTML=`<div class="card">${evaluationTable(rows)}</div>`; }
function evaluationTable(rows){ return table(rows,[{key:'evaluation_id',label:'Evaluation'},{key:'pass_fail',label:'Gate',render:r=>statusBadge(r.pass_fail)},{key:'score',label:'Score'},{key:'evaluator_type',label:'Evaluator'},{key:'agent_id',label:'Agent'},{key:'notes',label:'Notes'}]); }
async function renderAudit(){ setTitle('Audit Log','Append-only style activity record with before/after hashes and tamper_chain_hash placeholder.'); const rows=await api('/api/audit'); app.innerHTML=`<div class="card">${table(rows,[{key:'created_at',label:'Time'},{key:'actor_type',label:'Actor',render:r=>`${r.actor_type}:${r.actor_id}`},{key:'action',label:'Action'},{key:'entity_type',label:'Entity'},{key:'entity_id',label:'ID'},{key:'tamper_chain_hash',label:'Chain Hash',render:r=>`<code>${String(r.tamper_chain_hash||'').slice(0,16)}...</code>`}])}</div>`; }
async function renderIntegrations(){
  setTitle('Integrations','Connector status, export preview and external workflow handoff.');
  const [openclaw, hermes, status, preview] = await Promise.all([
    api('/api/integrations/openclaw/status'),
    api('/api/integrations/hermes/status'),
    api('/api/integrations/notion/status'),
    api('/api/integrations/notion/export-preview')
  ]);
  app.innerHTML = `<div class="grid-3">
    <div class="card"><h3>OpenClaw</h3>
      <p>${statusBadge(openclaw.config_exists ? 'ready' : 'missing_config')}</p>
      <pre>${escapeHtml(JSON.stringify(openclaw,null,2))}</pre>
      <div class="actions">
        <button onclick="importOpenClaw()">Import Local Data</button>
        <button onclick="probeOpenClaw()">Manual Probe</button>
      </div>
    </div>
    <div class="card"><h3>Hermes</h3>
      <p>${statusBadge(hermes.api_listening ? 'ready' : 'unavailable')}</p>
      <pre>${escapeHtml(JSON.stringify(hermes,null,2))}</pre>
      <div class="actions"><button onclick="probeHermes()">Manual Probe</button></div>
    </div>
    <div class="card"><h3>Notion Connection</h3>
      <p>${statusBadge(status.configured ? 'configured' : 'not_configured')}</p>
      <pre>${escapeHtml(JSON.stringify(status,null,2))}</pre>
      <div class="actions">
        <button onclick="exportNotion(true)">Dry Run</button>
        <button onclick="exportNotion(false)">Export to Notion</button>
      </div>
      <p class="muted">需要配置 NOTION_TOKEN，并设置 NOTION_PARENT_PAGE_ID 或 NOTION_DATABASE_ID。未配置时只返回预览，不会联网。</p>
    </div>
  </div>
  <div class="section card"><h3>Report Preview</h3>
    <p class="muted">Blocks: ${preview.block_count}</p>
    <pre>${escapeHtml(preview.markdown)}</pre>
  </div>`;
}
async function importOpenClaw(){
  const result = await api('/api/integrations/openclaw/import',{method:'POST',body:'{}'});
  toast('OpenClaw import complete');
  app.insertAdjacentHTML('afterbegin', `<div class="card section"><h3>OpenClaw Import Result</h3><pre>${escapeHtml(JSON.stringify(result,null,2))}</pre></div>`);
}
async function probeOpenClaw(){
  const result = await api('/api/integrations/openclaw/probe',{method:'POST',body:'{}'});
  toast(result.probe && result.probe.ok ? 'OpenClaw probe passed' : 'OpenClaw probe recorded failure');
  app.insertAdjacentHTML('afterbegin', `<div class="card section"><h3>OpenClaw Probe Result</h3><pre>${escapeHtml(JSON.stringify(result,null,2))}</pre></div>`);
}
async function probeHermes(){
  const result = await api('/api/integrations/hermes/probe',{method:'POST',body:'{}'});
  toast(result.status && result.status.api_listening ? 'Hermes probe passed' : 'Hermes unavailable recorded');
  app.insertAdjacentHTML('afterbegin', `<div class="card section"><h3>Hermes Probe Result</h3><pre>${escapeHtml(JSON.stringify(result,null,2))}</pre></div>`);
}
async function exportNotion(dryRun){
  const result = await api('/api/integrations/notion/export-report',{method:'POST',body:JSON.stringify({dry_run: dryRun, confirm_export: !dryRun})});
  if(result.url) toast('Notion page created');
  else toast(result.configured ? 'Notion dry run ready' : 'Notion not configured, preview returned');
  app.insertAdjacentHTML('afterbegin', `<div class="card section"><h3>Notion Export Result</h3><pre>${escapeHtml(JSON.stringify(result,null,2))}</pre></div>`);
}

async function renderWorkflows(){
  setTitle('AI Workflows','Real local AI work that writes back into Run Ledger, Evaluation, Runtime Events and Audit.');
  const [runs, events, evaluations, auditRows] = await Promise.all([
    api('/api/runs?task_id=tsk_local_ai_daily_brief'),
    api('/api/runtime-events'),
    api('/api/evaluations'),
    api('/api/audit')
  ]);
  const briefEvents = (events || []).filter(e => String(e.event_type || '').includes('local_ai_brief')).slice(0, 8);
  const briefEvaluations = (evaluations || []).filter(e => e.task_id === 'tsk_local_ai_daily_brief').slice(0, 8);
  const briefAudits = (auditRows || []).filter(a => String(a.action || '').includes('local_ai_brief')).slice(0, 8);
  app.innerHTML = `<div class="grid-2">
    <div class="card">
      <h3>Local AI Brief</h3>
      <p class="muted">Uses Agnesfallback CLI against safe structured MIS metrics. Default is dry-run; real run requires the server env HERMES_ALLOW_REAL_RUN=true and the explicit confirm button.</p>
      <div class="actions">
        <button onclick="runLocalBrief(false)">Dry-run Plan</button>
        <button class="ok" onclick="runLocalBrief(true)">Run Real Brief</button>
      </div>
      <p class="muted">No credentials, private messages, full prompts, or raw transcripts are stored.</p>
    </div>
    <div class="card">
      <h3>Latest Brief Runs</h3>${runTable(runs || [])}
    </div>
  </div>
  <div class="grid-3 section">
    <div class="card"><h3>Runtime Events</h3>${table(briefEvents,[{key:'created_at',label:'Time'},{key:'status',label:'Status',render:r=>statusBadge(r.status)},{key:'event_type',label:'Event'},{key:'output_summary',label:'Output'}])}</div>
    <div class="card"><h3>Evaluations</h3>${evaluationTable(briefEvaluations)}</div>
    <div class="card"><h3>Audit</h3>${table(briefAudits,[{key:'created_at',label:'Time'},{key:'action',label:'Action'},{key:'entity_id',label:'Entity'}])}</div>
  </div>`;
}

async function runLocalBrief(confirmRun){
  if(confirmRun && !confirm('Run a real local Agnesfallback brief now? The server must be started with HERMES_ALLOW_REAL_RUN=true.')) return;
  const result = await api('/api/workflows/local-brief',{method:'POST',body:JSON.stringify(confirmRun ? {confirm_run:true} : {})});
  toast(result.dry_run ? 'Dry-run plan recorded' : (result.ok ? 'Real AI brief recorded' : 'AI brief failed but was recorded'));
  const jump = result.run_id ? `<div class="actions"><button onclick="setRoute('runs/${result.run_id}')">Open Run</button><button onclick="setRoute('tasks/${result.task_id}')">Open Task</button></div>` : '';
  app.insertAdjacentHTML('afterbegin', `<div class="card section"><h3>Local AI Brief Result</h3>${jump}<pre>${escapeHtml(JSON.stringify(result,null,2))}</pre></div>`);
}
function renderSettings(){ setTitle('Settings','Default-off external calls, risk policy and future adapters.'); app.innerHTML=`<div class="grid-2"><div class="card"><h3>Runtime Policy</h3><pre>${escapeHtml(JSON.stringify({external_calls:'disabled',hidden_telemetry:'forbidden',high_risk_actions:'fail_closed',future_adapters:['claude_code','codex','openhands','crewai','langgraph','openclaw','hermes']},null,2))}</pre></div><div class="card"><h3>Default High-Risk Actions</h3><ul><li>shell.exec</li><li>github.push</li><li>email.send</li><li>file.delete</li><li>database.write</li></ul></div></div>`; }
async function exportJson(path, filename){ const data=await api(path); const blob=new Blob([JSON.stringify(data,null,2)],{type:'application/json'}); const url=URL.createObjectURL(blob); const a=document.createElement('a'); a.href=url; a.download=filename; a.click(); URL.revokeObjectURL(url); }

async function render(){
  renderNav();
  const parts = routeName().split('/'); const r = parts[0]; const id = parts[1];
  try {
    if(r==='dashboard') return renderDashboard();
    if(r==='agents' && id) return renderAgentDetail(id);
    if(r==='agents') return renderAgents();
    if(r==='tasks' && id) return renderTaskDetail(id);
    if(r==='tasks') return renderTasks();
    if(r==='runs' && id) return renderRunDetail(id);
    if(r==='runs') return renderRuns();
    if(r==='tool-calls') return renderToolCalls();
    if(r==='approvals') return renderApprovals();
    if(r==='memory') return renderMemory();
    if(r==='evaluations') return renderEvaluations();
    if(r==='audit') return renderAudit();
    if(r==='integrations') return renderIntegrations();
    if(r==='workflows') return renderWorkflows();
    if(r==='settings') return renderSettings();
    return renderDashboard();
  } catch(e) { app.innerHTML = `<div class="card"><h3>Error</h3><pre>${escapeHtml(e.stack || e.message)}</pre></div>`; }
}
refreshBtn.onclick = render;
window.onpopstate = render;
render();
