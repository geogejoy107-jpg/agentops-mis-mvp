import { useEffect, useState } from "react";
import { Cloud, Database, Radio, RefreshCw } from "lucide-react";
import { loadLocalReadiness, useLiveData } from "../data/liveApi";
import { usePreferences } from "../context/PreferencesContext";
import { StatusPill } from "../design-system/Pills";

export function ContextBar() {
  const { locale } = usePreferences();
  const { data, loading, error, refresh } = useLiveData(() => loadLocalReadiness(), []);
  const [checkedAt, setCheckedAt] = useState<string | null>(null);

  useEffect(() => {
    if (data || error) setCheckedAt(new Date().toISOString());
  }, [data, error]);

  const environment = import.meta.env.VITE_AGENTOPS_ENV || "Local";
  const status = error ? "unavailable" : loading ? "checking" : data?.status || "unknown";

  return (
    <div className="flex min-h-[var(--ui-context-height)] items-center gap-3 overflow-x-auto border-b px-3 text-[11px] sm:px-5" style={{ background: "var(--ui-surface-2)", borderColor: "var(--ui-border)", color: "var(--ui-text-muted)" }}>
      <span className="inline-flex shrink-0 items-center gap-1.5">
        <Database size={12} />
        {locale === "zh" ? "工作区" : "Workspace"}: <strong style={{ color: "var(--ui-text)" }}>{data?.workspace_id || "local-demo"}</strong>
      </span>
      <span className="h-3 w-px shrink-0" style={{ background: "var(--ui-border)" }} />
      <span className="inline-flex shrink-0 items-center gap-1.5">
        <Cloud size={12} />
        {locale === "zh" ? "环境" : "Environment"}: <strong style={{ color: "var(--ui-text)" }}>{environment}</strong>
      </span>
      <span className="h-3 w-px shrink-0" style={{ background: "var(--ui-border)" }} />
      <span className="inline-flex shrink-0 items-center gap-1.5"><Radio size={12} />{locale === "zh" ? "运行健康" : "Runtime health"}</span>
      <StatusPill status={status} label={status === "checking" ? (locale === "zh" ? "检查中" : "Checking") : undefined} />
      <span className="ml-auto inline-flex shrink-0 items-center gap-1.5" title={checkedAt || undefined}>
        {locale === "zh" ? "数据" : "Data"}: {checkedAt ? new Date(checkedAt).toLocaleTimeString() : "—"}
        <button type="button" onClick={refresh} className="ui-v2-interactive rounded p-1" aria-label={locale === "zh" ? "刷新上下文" : "Refresh context"}>
          <RefreshCw size={12} className={loading ? "animate-spin" : ""} />
        </button>
      </span>
    </div>
  );
}
