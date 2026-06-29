import * as React from "react";
import { Link, NavLink, Outlet } from "react-router-dom";
import {
  Activity,
  Briefcase,
  Check,
  Home,
  Library,
  Menu,
  Monitor,
  Moon,
  ScrollText,
  Settings,
  Sun,
  Workflow,
  X
} from "lucide-react";
import { useQuery } from "@tanstack/react-query";

import { getHealth } from "@/api/health";
import { listJobs } from "@/api/jobs";
import { Button } from "@/components/ui/button";
import { StatusBadge } from "@/components/StatusBadge";
import { useUiStore } from "@/hooks/useUiStore";
import type { ThemeMode } from "@/lib/theme";
import { cn, percent } from "@/lib/utils";

const navItems = [
  { to: "/", label: "Dashboard", icon: Home },
  { to: "/workflows", label: "Workflows", icon: Workflow },
  { to: "/library", label: "Library", icon: Library },
  { to: "/jobs", label: "Jobs", icon: Briefcase },
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
                health.isSuccess
                  ? "bg-[hsl(var(--success))]"
                  : health.isError
                    ? "bg-destructive"
                    : "bg-[hsl(var(--warning))]"
              )}
            />
            <span className="text-xs text-muted-foreground">
              {health.isSuccess ? `API ${health.data.version}` : health.isError ? "API offline" : "Checking API"}
            </span>
          </div>
        </div>
        <ThemeModeMenu />
      </header>

      <aside className="fixed bottom-0 left-0 top-14 z-30 hidden w-56 flex-col border-r bg-card lg:flex">
        <Navigation />
        <ActiveJobStatus job={activeJob} />
      </aside>

      {sidebarOpen ? (
        <div className="fixed inset-0 z-50 lg:hidden">
          <button
            type="button"
            className="absolute inset-0 bg-foreground/20"
            aria-label="Close navigation"
            onClick={() => setSidebarOpen(false)}
          />
          <aside className="absolute bottom-0 left-0 top-0 flex w-64 flex-col border-r bg-card shadow-lg">
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
            <ActiveJobStatus job={activeJob} onNavigate={() => setSidebarOpen(false)} />
          </aside>
        </div>
      ) : null}

      <main className="pt-14 lg:pl-56">
        <Outlet />
      </main>
    </div>
  );
}

function ThemeModeMenu(): JSX.Element {
  const themeMode = useUiStore((state) => state.themeMode);
  const setThemeMode = useUiStore((state) => state.setThemeMode);
  const [open, setOpen] = React.useState(false);
  const menuRef = React.useRef<HTMLDivElement | null>(null);
  const options: Array<{ value: ThemeMode; label: string; icon: typeof Monitor }> = [
    { value: "system", label: "System", icon: Monitor },
    { value: "light", label: "Light", icon: Sun },
    { value: "dark", label: "Dark", icon: Moon }
  ];
  const current = options.find((option) => option.value === themeMode) ?? options[0];
  const CurrentIcon = current.icon;

  React.useEffect(() => {
    if (!open) {
      return;
    }
    const closeOnOutsideClick = (event: MouseEvent) => {
      if (!menuRef.current?.contains(event.target as Node)) {
        setOpen(false);
      }
    };
    document.addEventListener("mousedown", closeOnOutsideClick);
    return () => document.removeEventListener("mousedown", closeOnOutsideClick);
  }, [open]);

  return (
    <div ref={menuRef} className="relative">
      <Button
        type="button"
        variant="ghost"
        size="icon"
        aria-label={`Theme: ${current.label}`}
        title={`Theme: ${current.label}`}
        aria-expanded={open}
        onClick={() => setOpen((value) => !value)}
      >
        <CurrentIcon className="h-5 w-5" aria-hidden="true" />
      </Button>
      {open ? (
        <div className="absolute right-0 top-11 z-50 w-40 rounded-md border bg-card p-1 text-sm shadow-lg">
          {options.map((option) => {
            const Icon = option.icon;
            const selected = option.value === themeMode;
            return (
              <button
                key={option.value}
                type="button"
                className={cn(
                  "flex h-9 w-full items-center gap-2 rounded-sm px-2 text-left text-muted-foreground hover:bg-muted hover:text-foreground",
                  selected && "bg-secondary text-secondary-foreground"
                )}
                onClick={() => {
                  setThemeMode(option.value);
                  setOpen(false);
                }}
              >
                <Icon className="h-4 w-4" aria-hidden="true" />
                <span className="flex-1">{option.label}</span>
                {selected ? <Check className="h-4 w-4" aria-hidden="true" /> : null}
              </button>
            );
          })}
        </div>
      ) : null}
    </div>
  );
}

function Navigation({ onNavigate }: { onNavigate?: () => void }): JSX.Element {
  return (
    <nav className="flex-1 space-y-1 p-3">
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

type ActiveJob = Awaited<ReturnType<typeof listJobs>>["items"][number];

function ActiveJobStatus({ job, onNavigate }: { job?: ActiveJob; onNavigate?: () => void }): JSX.Element {
  if (!job) {
    return (
      <div className="border-t p-3">
        <div className="rounded-md border bg-muted/30 px-3 py-2 text-xs text-muted-foreground">
          No active job
        </div>
      </div>
    );
  }

  const completed = job.completed_files + job.skipped_files + job.failed_files;
  const progress = percent(completed, job.total_files);
  const target = job.input_user_id ? `User ${job.input_user_id}` : `Artwork ${job.input_artwork_id}`;

  return (
    <div className="border-t p-3">
      <Link
        to="/jobs"
        className="block rounded-md border bg-background px-3 py-2 transition-colors hover:bg-muted"
        title={`Open active job: ${target}`}
        onClick={onNavigate}
      >
        <div className="flex items-center gap-2">
          <Activity className="h-4 w-4 shrink-0 text-primary" aria-hidden="true" />
          <span className="min-w-0 flex-1 truncate text-xs font-medium">{target}</span>
          <span className="text-xs text-muted-foreground">{progress}%</span>
        </div>
        <div className="mt-2 flex items-center justify-between gap-2">
          <StatusBadge status={job.status} />
          <span className="truncate text-xs text-muted-foreground">{completed} / {job.total_files} files</span>
        </div>
      </Link>
    </div>
  );
}
