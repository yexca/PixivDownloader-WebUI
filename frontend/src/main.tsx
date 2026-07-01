import React from "react";
import ReactDOM from "react-dom/client";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { createBrowserRouter, Navigate, RouterProvider } from "react-router-dom";

import { AppShell } from "@/components/AppShell";
import { ToastProvider } from "@/components/ToastProvider";
import { useUiStore } from "@/hooks/useUiStore";
import { watchSystemTheme } from "@/lib/theme";
import "./index.css";

const AboutPage = React.lazy(() => import("@/pages/AboutPage").then((module) => ({ default: module.AboutPage })));
const ArtistDetailPage = React.lazy(() =>
  import("@/pages/ArtistDetailPage").then((module) => ({ default: module.ArtistDetailPage }))
);
const DashboardPage = React.lazy(() =>
  import("@/pages/DashboardPage").then((module) => ({ default: module.DashboardPage }))
);
const JobsPage = React.lazy(() => import("@/pages/JobsPage").then((module) => ({ default: module.JobsPage })));
const LibraryPage = React.lazy(() =>
  import("@/pages/LibraryPage").then((module) => ({ default: module.LibraryPage }))
);
const LogsPage = React.lazy(() => import("@/pages/LogsPage").then((module) => ({ default: module.LogsPage })));
const RunsPage = React.lazy(() => import("@/pages/RunsPage").then((module) => ({ default: module.RunsPage })));
const SettingsPage = React.lazy(() =>
  import("@/pages/SettingsPage").then((module) => ({ default: module.SettingsPage }))
);
const WorkflowsPage = React.lazy(() =>
  import("@/pages/WorkflowsPage").then((module) => ({ default: module.WorkflowsPage }))
);

watchSystemTheme(() => useUiStore.getState().refreshResolvedTheme());

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      retry: 1,
      staleTime: 5000
    }
  }
});

function suspensePage(page: React.ReactNode): JSX.Element {
  return (
    <React.Suspense
      fallback={
        <div className="p-4 sm:p-6">
          <div className="surface p-4 text-sm text-muted-foreground">Loading page...</div>
        </div>
      }
    >
      {page}
    </React.Suspense>
  );
}

const router = createBrowserRouter([
  {
    path: "/",
    element: <AppShell />,
    children: [
      { index: true, element: suspensePage(<DashboardPage />) },
      { path: "workflows", element: suspensePage(<WorkflowsPage />) },
      { path: "runs", element: suspensePage(<RunsPage />) },
      { path: "library", element: suspensePage(<LibraryPage />) },
      { path: "artists/:artistId", element: suspensePage(<ArtistDetailPage />) },
      { path: "jobs", element: suspensePage(<JobsPage />) },
      { path: "jobs/schedules", element: <Navigate to="/workflows" replace /> },
      { path: "settings", element: suspensePage(<SettingsPage />) },
      { path: "logs", element: suspensePage(<LogsPage />) },
      { path: "about", element: suspensePage(<AboutPage />) }
    ]
  }
]);

ReactDOM.createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <QueryClientProvider client={queryClient}>
      <ToastProvider>
        <RouterProvider router={router} />
      </ToastProvider>
    </QueryClientProvider>
  </React.StrictMode>
);
