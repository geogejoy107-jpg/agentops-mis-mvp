import { FormEvent, useCallback, useEffect, useMemo, useState } from "react";
import "./research-lab.css";

type RecordValue = { id?: string; research_project_id?: string; experiment_id?: string; status?: string; name?: string; [key: string]: unknown };
type Envelope = { api_version: string; state?: "ready" | "degraded" | "unavailable"; data?: RecordValue[] | RecordValue; error?: { code: string; message?: string } };
type Surface = { slug: string; label: string; resource: string; writable?: boolean };

const governedActions: Record<string, string[]> = {
  "trial-matrix": ["attempts/start"], "job-attempt": ["attempts/execute", "attempts/cancel", "attempts/reconcile"],
  literature: ["literature/search"], budgets: ["budgets/evaluate"], "claims-evidence": ["claims/decide", "evidence/invalidate"],
  memory: ["memory/candidate"], "runtime-health": ["runtime/dispatch", "runtime/resume"], settings: ["migration/dry-run", "migration/apply", "migration/restore"], manuscripts: ["exports/bdci"],
};

const surfaces: Surface[] = [
  { slug: "home", label: "Research Home", resource: "health" },
  { slug: "projects", label: "Projects", resource: "projects", writable: true },
  { slug: "experiments", label: "Experiments", resource: "experiments", writable: true },
  { slug: "experiment-contract", label: "Experiment Contract", resource: "experiments/{id}" },
  { slug: "trial-matrix", label: "Trial Matrix", resource: "experiments/{id}/trials" },
  { slug: "job-attempt", label: "JobAttempt Detail", resource: "attempts/{id}" },
  { slug: "live-logs", label: "Live Logs", resource: "attempts/{id}/logs" },
  { slug: "metrics", label: "Metrics", resource: "experiments/{id}/metrics" },
  { slug: "checkpoints", label: "Checkpoints", resource: "attempts/{id}/checkpoints" },
  { slug: "compute-targets", label: "Compute Targets", resource: "compute-targets" },
  { slug: "budgets", label: "Budgets", resource: "budgets" },
  { slug: "approvals", label: "Approvals", resource: "approvals" },
  { slug: "literature", label: "Literature", resource: "literature" },
  { slug: "claims-evidence", label: "Claims / Evidence", resource: "claims" },
  { slug: "manuscripts", label: "Manuscripts", resource: "manuscripts" },
  { slug: "memory", label: "Memory", resource: "memory" },
  { slug: "runtime-health", label: "Runtime Health", resource: "runtime/health" },
  { slug: "settings", label: "Settings", resource: "settings" },
];

function initialSlug() {
  const value = typeof window === "undefined" ? "home" : window.location.pathname.split("/").filter(Boolean).at(-1) ?? "home";
  return surfaces.some((item) => item.slug === value) ? value : "home";
}

function currentDeepLinkId() {
  return typeof window === "undefined" ? "" : new URLSearchParams(window.location.search).get("id") ?? "";
}

export default function ResearchLabExtension() {
  const [slug, setSlug] = useState(initialSlug);
  const [payload, setPayload] = useState<Envelope | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [permissionDenied, setPermissionDenied] = useState(false);
  const [busy, setBusy] = useState(false);
  const [name, setName] = useState("");
  const [contractJson, setContractJson] = useState("{}");
  const [actionJson, setActionJson] = useState('{"idempotency_key":""}');
  const [deepLinkId, setDeepLinkId] = useState(currentDeepLinkId);
  const surface = useMemo(() => surfaces.find((item) => item.slug === slug) ?? surfaces[0], [slug]);
  const resolvedResource = surface.resource.includes("{id}") ? (deepLinkId ? surface.resource.replace("{id}", encodeURIComponent(deepLinkId)) : surface.resource.split("/{id}")[0]) : surface.resource;

  const load = useCallback(async () => {
    setLoading(true); setError(""); setPermissionDenied(false);
    try {
      const response = await fetch(`/api/v1/templates/research_lab/${resolvedResource}`, { credentials: "same-origin", headers: { Accept: "application/json" } });
      const body = await response.json() as Envelope;
      if (response.status === 401 || response.status === 403) { setPermissionDenied(true); setPayload(body); return; }
      if (!response.ok) throw new Error(body.error?.code ?? `HTTP ${response.status}`);
      setPayload(body);
    } catch (cause) { setPayload(null); setError(cause instanceof Error ? cause.message : "research.ui_load_failed"); }
    finally { setLoading(false); }
  }, [resolvedResource]);

  useEffect(() => void load(), [load]);
  useEffect(() => {
    const onPopState = () => { setSlug(initialSlug()); setDeepLinkId(currentDeepLinkId()); };
    window.addEventListener("popstate", onPopState);
    return () => window.removeEventListener("popstate", onPopState);
  }, []);

  function navigate(next: string) {
    setSlug(next); setPayload(null);
    const query = deepLinkId && (surfaces.find((item) => item.slug === next)?.resource.includes("{id}")) ? `?id=${encodeURIComponent(deepLinkId)}` : "";
    window.history.pushState({}, "", `/solutions/research_lab/${next}${query}`);
  }

  async function create(event: FormEvent) {
    event.preventDefault(); if (!surface.writable || !name.trim()) return;
    setBusy(true); setError("");
    try {
      const resource = surface.resource;
      const body = resource === "projects" ? { name, research_contract: JSON.parse(contractJson), idempotency_key: crypto.randomUUID() } : { ...JSON.parse(contractJson), idempotency_key: crypto.randomUUID() };
      const response = await fetch(`/api/v1/templates/research_lab/${resource}`, { method: "POST", credentials: "same-origin", headers: { "Content-Type": "application/json", Accept: "application/json" }, body: JSON.stringify(body) });
      const result = await response.json() as Envelope;
      if (response.status === 401 || response.status === 403) { setPermissionDenied(true); setPayload(result); return; }
      if (!response.ok) throw new Error(result.error?.code ?? `HTTP ${response.status}`);
      setName(""); await load();
    } catch (cause) { setError(cause instanceof Error ? cause.message : "research.ui_action_failed"); }
    finally { setBusy(false); }
  }

  async function executeAction(operation: string) {
    setBusy(true); setError("");
    try {
      const body = JSON.parse(actionJson) as Record<string, unknown>;
      if (!body.idempotency_key) throw new Error("research.idempotency_key_missing");
      const response = await fetch(`/api/v1/templates/research_lab/${operation}`, { method: "POST", credentials: "same-origin", headers: { "Content-Type": "application/json", Accept: "application/json" }, body: JSON.stringify(body) });
      const result = await response.json() as Envelope;
      if (response.status === 401 || response.status === 403) { setPermissionDenied(true); setPayload(result); return; }
      if (!response.ok) throw new Error(result.error?.code ?? `HTTP ${response.status}`);
      setPayload(result);
    } catch (cause) { setError(cause instanceof Error ? cause.message : "research.ui_action_failed"); }
    finally { setBusy(false); }
  }

  const items = Array.isArray(payload?.data) ? payload.data : payload?.data ? [payload.data] : [];
  const degraded = payload?.state === "degraded" || payload?.state === "unavailable";
  return <section className="research-app" aria-label="Research Lab">
    <header><div><p>Governed Research Production</p><h1>Research Lab</h1></div><strong>{payload?.state ?? (loading ? "loading" : "ready")}</strong></header>
    <nav aria-label="Research sections">{surfaces.map((item) => <button type="button" className={item.slug === slug ? "active" : ""} key={item.slug} onClick={() => navigate(item.slug)}>{item.label}</button>)}</nav>
    <main><h2>{surface.label}</h2>
      {loading && <div role="status">Loading MIS Core read model…</div>}
      {permissionDenied && <div role="alert"><h3>Permission denied</h3><p>Request the namespaced permission through MIS Core.</p></div>}
      {error && <div role="alert"><code>{error}</code><button type="button" onClick={() => void load()}>Retry</button></div>}
      {surface.resource.includes("{id}") && !deepLinkId && <div role="status"><h3>Select a governed record</h3><p>Open this deep link with a Core-backed <code>?id=…</code> reference.</p></div>}
      {degraded && <div role="status"><h3>Degraded — no false success</h3><p>Open Runtime Health, resolve external gates, then reconcile.</p></div>}
      {!loading && !error && !permissionDenied && !degraded && items.length === 0 && <div><h3>No records</h3><p>Create or configure the governed inputs for this surface.</p></div>}
      {items.length > 0 && <ol>{items.map((item, index) => <li key={String(item.id ?? item.research_project_id ?? item.experiment_id ?? index)}><strong>{String(item.name ?? item.id ?? item.research_project_id ?? item.experiment_id ?? "Record")}</strong><pre>{JSON.stringify(item, null, 2)}</pre></li>)}</ol>}
      {surface.writable && <form onSubmit={create}>{surface.resource === "projects" && <label>Name<input value={name} onChange={(event) => setName(event.target.value)} /></label>}<label>Governed contract JSON<textarea value={contractJson} onChange={(event) => setContractJson(event.target.value)} /></label><button disabled={busy || (surface.resource === "projects" && !name.trim())}>{busy ? "Submitting…" : "Create through API"}</button></form>}
      {(governedActions[slug] ?? []).length > 0 && <section aria-label="Governed actions"><h3>Governed actions</h3><label>Prepared request JSON<textarea value={actionJson} onChange={(event) => setActionJson(event.target.value)} /></label><div>{governedActions[slug].map((operation) => <button type="button" disabled={busy} key={operation} onClick={() => void executeAction(operation)}>{operation}</button>)}</div></section>}
    </main>
  </section>;
}
