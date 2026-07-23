import {
  controlPlaneMode,
  isProductionDeployment,
} from "@/server/controlPlane/config";

export const dynamic = "force-dynamic";

export default function HomePage() {
  const production = isProductionDeployment();
  const mode = controlPlaneMode();

  return (
    <main className="controlPlaneHome">
      <header className="controlPlaneHeader">
        <div className="brand">
          <span className="brandMark" aria-hidden="true">A</span>
          <div>
            <strong>AgentOps MIS</strong>
            <span>Control Plane</span>
          </div>
        </div>
        <span className={production ? "statusChip live" : "statusChip local"}>
          {production ? "Production" : "Free Local"}
        </span>
      </header>

      <section className="controlPlaneOverview" aria-labelledby="control-plane-title">
        <p className="eyebrow">Runtime boundary</p>
        <h1 id="control-plane-title">Production control plane</h1>
        <dl className="controlPlaneFacts">
          <div>
            <dt>Route owner</dt>
            <dd>Next.js / TypeScript</dd>
          </div>
          <div>
            <dt>Control plane</dt>
            <dd>{mode === "postgres" ? "PostgreSQL" : "Free Local proxy"}</dd>
          </div>
          <div>
            <dt>Python production proxy</dt>
            <dd>{production ? "Blocked" : "Local only"}</dd>
          </div>
        </dl>
      </section>
    </main>
  );
}
