import { Link } from "react-router-dom";
import { Download, RefreshCw } from "lucide-react";
import { useQuery } from "@tanstack/react-query";

import { listArtists } from "@/api/artists";
import { listJobs } from "@/api/jobs";
import { Button } from "@/components/ui/button";
import { DataState } from "@/components/DataState";
import { JobProgress } from "@/components/JobProgress";
import { JobTable } from "@/components/JobTable";
import { PageHeader } from "@/components/PageHeader";
import { useJobStream } from "@/hooks/useJobStream";

export function DashboardPage(): JSX.Element {
  const jobs = useQuery({
    queryKey: ["jobs", "all", 10],
    queryFn: () => listJobs({ limit: 10 }),
    refetchInterval: 4000
  });
  const artists = useQuery({
    queryKey: ["artists", "dashboard"],
    queryFn: () => listArtists({ limit: 50 })
  });
  const activeJob = jobs.data?.items.find((job) => job.status === "running" || job.status === "queued");
  const stream = useJobStream(activeJob?.id);
  const downloadedFiles =
    artists.data?.items.reduce((total, artist) => total + artist.downloaded_file_count, 0) ?? 0;
  const failedFiles = artists.data?.items.reduce((total, artist) => total + artist.failed_file_count, 0) ?? 0;
  const artworkCount = artists.data?.items.reduce((total, artist) => total + artist.artwork_count, 0) ?? 0;

  return (
    <>
      <PageHeader
        title="Dashboard"
        description="Current queue, library totals, and recent activity."
        actions={
          <Button asChild>
            <Link to="/download">
              <Download className="h-4 w-4" aria-hidden="true" />
              New Download
            </Link>
          </Button>
        }
      />
      <div className="space-y-4 p-4 sm:p-6">
        <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
          <Metric label="Artists" value={artists.data?.total ?? 0} loading={artists.isLoading} />
          <Metric label="Artworks" value={artworkCount} loading={artists.isLoading} />
          <Metric label="Downloaded files" value={downloadedFiles} loading={artists.isLoading} />
          <Metric label="Failed files" value={failedFiles} loading={artists.isLoading} />
        </div>

        {activeJob ? (
          <JobProgress job={activeJob} message={stream.lastMessage?.message} />
        ) : (
          <DataState
            title="No active download"
            description="Start a user or artwork download when you are ready."
            actionLabel="Open Download"
            onAction={() => {
              window.location.href = "/download";
            }}
          />
        )}

        <section>
          <div className="mb-3 flex items-center justify-between">
            <h2 className="text-sm font-semibold">Recent Jobs</h2>
            <Button
              type="button"
              variant="ghost"
              size="sm"
              onClick={() => void jobs.refetch()}
              disabled={jobs.isFetching}
            >
              <RefreshCw className="h-4 w-4" aria-hidden="true" />
              Refresh
            </Button>
          </div>
          {jobs.isLoading ? (
            <DataState title="Loading jobs" variant="loading" />
          ) : jobs.isError ? (
            <DataState title="Could not load jobs" description={jobs.error.message} variant="error" />
          ) : jobs.data.items.length === 0 ? (
            <DataState title="No jobs yet" description="Started downloads will appear here." />
          ) : (
            <JobTable jobs={jobs.data.items} />
          )}
        </section>
      </div>
    </>
  );
}

function Metric({
  label,
  value,
  loading
}: {
  label: string;
  value: number;
  loading: boolean;
}): JSX.Element {
  return (
    <div className="surface p-4">
      <p className="text-xs font-medium uppercase text-muted-foreground">{label}</p>
      <p className="mt-2 text-2xl font-semibold">{loading ? "-" : value.toLocaleString()}</p>
    </div>
  );
}
