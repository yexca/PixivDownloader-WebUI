import React from "react";
import ReactDOM from "react-dom/client";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { createBrowserRouter, Navigate, RouterProvider } from "react-router-dom";

import { AppShell } from "@/components/AppShell";
import { ToastProvider } from "@/components/ToastProvider";
import { ArtistDetailPage } from "@/pages/ArtistDetailPage";
import { DashboardPage } from "@/pages/DashboardPage";
import { JobsPage } from "@/pages/JobsPage";
import { LibraryPage } from "@/pages/LibraryPage";
import { LogsPage } from "@/pages/LogsPage";
import { SettingsPage } from "@/pages/SettingsPage";
import { WorkflowsPage } from "@/pages/WorkflowsPage";
import "./index.css";

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      retry: 1,
      staleTime: 5000
    }
  }
});

const router = createBrowserRouter([
  {
    path: "/",
    element: <AppShell />,
    children: [
      { index: true, element: <DashboardPage /> },
      { path: "workflows", element: <WorkflowsPage /> },
      { path: "library", element: <LibraryPage /> },
      { path: "artists/:artistId", element: <ArtistDetailPage /> },
      { path: "jobs", element: <JobsPage /> },
      { path: "jobs/schedules", element: <Navigate to="/workflows" replace /> },
      { path: "settings", element: <SettingsPage /> },
      { path: "logs", element: <LogsPage /> }
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
