import { Outlet } from "react-router";
import { Sidebar } from "./Sidebar";
import { Topbar } from "./Topbar";
import { usePreferences } from "../../context/PreferencesContext";

export function AppShell() {
  const { theme } = usePreferences();

  return (
    <div
      className={`app-shell theme-${theme} flex h-screen w-screen overflow-hidden`}
      style={{ background: "var(--mis-bg)", color: "var(--mis-text)" }}
    >
      <Sidebar />
      <div className="flex flex-col flex-1 min-w-0 overflow-hidden">
        <Topbar />
        <main className="app-main flex-1 overflow-y-auto p-4 lg:p-5">
          <Outlet />
        </main>
      </div>
    </div>
  );
}
