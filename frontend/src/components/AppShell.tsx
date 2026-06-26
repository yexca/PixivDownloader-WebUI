import { NavLink, Outlet } from "react-router-dom";
import { Activity, Briefcase, CalendarClock, Download, Home, Library, Menu, ScrollText, Settings, X } from "lucide-react";
import { useQuery } from "@tanstack/react-query";

import { getHealth } from "@/api/health";
import { listJobs } from "@/api/jobs";
import { Button } from "@/components/ui/button";
import { StatusBadge } from "@/components/StatusBadge";
import { useUiStore } from "@/hooks/useUiStore";
import { cn, percent } from "@/lib/utils";

const navItems = [
  { to: "/", label: "Dashboard", icon: Home },
  { to: "/download", label: "Download", icon: Download },
  { to: "/library", label: "Library", icon: Library },
  { to: "/jobs", label: "Jobs", icon: Briefcase },
  { to: "/jobs/schedules", label: "Schedules", icon: CalendarClock },
  { to: "/settings", label: "Settings", icon: Settings },
  { to: "/logs", label: "Logs", icon: ScrollText }
];

export function AppShell(): JSX.Element {
  const sidebarOpen = useUiStore((state) => state.sidebarOpen);
  const setSidebarOpen = useUiStore((state) => state.setSidebarOpen);
  const health = useQuery({ queryKey: ["health"], queryFn: getHealth, refetchInterval: 30000 });
  const activeJobs = useQuery({
    queryKey: ["jobs", "active", 5],
    queryFn: () => listJobs({ limit: 5 }),
    refetchInterval: 3000
  });
  const activeJob = activeJobs.data?.items.find(
    (job) => job.status === "running" || job.status === "queued"
  );

  return (
    <div className="min-h-screen bg-background">
      <header className="fixed inset-x-0 top-0 z-40 flex h-14 items-center border-b bg-card px-3 sm:px-4">
        <Button
          type="button"
          variant="ghost"
          size="icon"
          className="mr-2 lg:hidden"
          aria-label="Open navigation"
          title="Open navigation"
          onClick={() => setSidebarOpen(true)}
        >
          <Menu className="h-5 w-5" aria-hidden="true" />
        </Button>
        <div className="flex min-w-0 flex-1 items-center gap-3">
          <div className="min-w-0">
            <p className="truncate text-sm font-semibold">Pixiv Downloader</p>
            <p className="truncate text-xs text-muted-foreground">Local WebUI</p>
          </div>
          <div className="hidden items-center gap-2 border-l pl-3 sm:flex">
            <span
              className={cn(
                "h-2 w-2 rounded-full",
                health.isSuccess ? "bg-emerald-500" : health.isError ? "bg-destructive" : "bg-amber-500"
              )}
            />
            <span className="text-xs text-muted-foreground">
              {health.isSuccess ? `API ${health.data.version}` : health.isError ? "API offline" : "Checking API"}
            </span>
          </div>
        </div>
        {activeJob ? (
          <div className="hidden items-center gap-2 md:flex">
            <Activity className="h-4 w-4 text-primary" aria-hidden="true" />
            <span className="max-w-44 truncate text-xs text-muted-foreground">
              {activeJob.input_user_id ? `User ${activeJob.input_user_id}` : `Artwork ${activeJob.input_artwork_id}`}
            </span>
            <StatusBadge status={activeJob.status} />
            <span className="w-10 text-right text-xs text-muted-foreground">
              {percent(
                activeJob.completed_files + activeJob.skipped_files + activeJob.failed_files,
                activeJob.total_files
              )}
              %
            </span>
          </div>
        ) : (
          <span className="hidden text-xs text-muted-foreground md:inline">No active job</span>
        )}
      </header>

      <aside className="fixed bottom-0 left-0 top-14 z-30 hidden w-56 border-r bg-card lg:block">
        <Navigation />
      </aside>

      {sidebarOpen ? (
        <div className="fixed inset-0 z-50 lg:hidden">
          <button
            type="button"
            className="absolute inset-0 bg-foreground/20"
            aria-label="Close navigation"
            onClick={() => setSidebarOpen(false)}
          />
          <aside className="absolute bottom-0 left-0 top-0 w-64 border-r bg-card shadow-lg">
            <div className="flex h-14 items-center justify-between border-b px-4">
              <span className="text-sm font-semibold">Navigation</span>
              <Button
                type="button"
                variant="ghost"
                size="icon"
                aria-label="Close navigation"
                title="Close"
                onClick={() => setSidebarOpen(false)}
              >
                <X className="h-5 w-5" aria-hidden="true" />
              </Button>
            </div>
            <Navigation onNavigate={() => setSidebarOpen(false)} />
          </aside>
        </div>
      ) : null}

      <main className="pt-14 lg:pl-56">
        <Outlet />
      </main>
    </div>
  );
}

function Navigation({ onNavigate }: { onNavigate?: () => void }): JSX.Element {
  return (
    <nav className="space-y-1 p-3">
      {navItems.map((item) => (
        <NavLink
          key={item.to}
          to={item.to}
          end
          onClick={onNavigate}
          className={({ isActive }) =>
            cn(
              "flex h-10 items-center gap-3 rounded-md px-3 text-sm font-medium text-muted-foreground transition-colors hover:bg-muted hover:text-foreground",
              isActive && "bg-secondary text-secondary-foreground"
            )
          }
        >
          <item.icon className="h-4 w-4" aria-hidden="true" />
          {item.label}
        </NavLink>
      ))}
    </nav>
  );
}
