import * as React from "react";
import { useNavigate, useSearchParams } from "react-router-dom";
import {
  AlertTriangle,
  Download,
  ExternalLink,
  RefreshCw,
  RotateCcw,
  Search
} from "lucide-react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import {
  listArtists,
  listLocalTags,
  retryFailedArtist,
  syncArtist,
  type ArtistSummary
} from "@/api/artists";
import { createDownloadJob, type DownloadCreateRequest } from "@/api/downloads";
import { listJobs, type Job } from "@/api/jobs";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Select } from "@/components/ui/select";
import { DataState } from "@/components/DataState";
import { PageHeader } from "@/components/PageHeader";
import { Pagination } from "@/components/Pagination";
import { useToast } from "@/components/ToastProvider";
import { actionIconClass, formatDate } from "@/lib/utils";

type ArtistRunningJob = {
  type: "sync" | "download" | "retry";
  status: Job["status"];
};
type ArtistJobState = Partial<Record<ArtistRunningJob["type"], ArtistRunningJob>>;

export function ArtistsPage(): JSX.Element {
  const [searchParams, setSearchParams] = useSearchParams();
  const submittedQuery = searchParams.get("q") ?? "";
  const selectedTag = searchParams.get("localTag") ?? "";
  const accountStatus = searchParams.get("accountStatus") ?? "";
  const updateState = searchParams.get("updateState") ?? "";
  const fileState = searchParams.get("fileState") ?? "";
  const sort = searchParams.get("sort") ?? "updated_desc";
  const page = Math.max(1, Number(searchParams.get("page") || "1"));
  const pageSize = Math.max(1, Number(searchParams.get("pageSize") || "24"));
  const [query, setQuery] = React.useState(submittedQuery);

  const artists = useQuery({
    queryKey: ["artists-directory", submittedQuery, selectedTag, accountStatus, updateState, fileState, sort, pageSize, page],
    queryFn: () =>
      listArtists({
        q: submittedQuery || undefined,
        local_tag: selectedTag || undefined,
        account_status: accountStatus || undefined,
        update_state: updateState || undefined,
        file_state: fileState || undefined,
        sort,
        limit: pageSize,
        offset: (page - 1) * pageSize
      })
  });
  const tags = useQuery({ queryKey: ["local-tags"], queryFn: listLocalTags });
  const activeJobs = useQuery({
    queryKey: ["jobs", "artists-active", 100],
    queryFn: () => listJobs({ limit: 100 }),
    refetchInterval: 4000
  });

  React.useEffect(() => {
    setQuery(submittedQuery);
  }, [submittedQuery]);

  const setFilter = (key: string, value: string) => {
    const nextParams = new URLSearchParams(searchParams);
    if (value) {
      nextParams.set(key, value);
    } else {
      nextParams.delete(key);
    }
    nextParams.set("page", "1");
    setSearchParams(nextParams, { replace: true });
  };
  const setPage = (nextPage: number) => {
    const nextParams = new URLSearchParams(searchParams);
    nextParams.set("page", String(nextPage));
    setSearchParams(nextParams, { replace: true });
  };
  const setPageSize = (nextPageSize: number) => {
    const nextParams = new URLSearchParams(searchParams);
    nextParams.set("pageSize", String(nextPageSize));
    nextParams.set("page", "1");
    setSearchParams(nextParams, { replace: true });
  };

  const items = artists.data?.items ?? [];
  const artistJobs = React.useMemo(() => artistJobMap(activeJobs.data?.items ?? []), [activeJobs.data?.items]);

  return (
    <>
      <PageHeader
        title="Artists"
        description="Browse known Pixiv artists, open their works, and start artist shortcuts."
        actions={
          <Button type="button" variant="outline" onClick={() => void artists.refetch()} disabled={artists.isFetching}>
            <RefreshCw className="h-4 w-4" aria-hidden="true" />
            Refresh
          </Button>
        }
      />
      <div className="space-y-4 p-4 sm:p-6">
        <form
          className="surface grid gap-3 p-3 lg:grid-cols-[minmax(240px,1fr)_repeat(5,minmax(150px,auto))_auto]"
          onSubmit={(event) => {
            event.preventDefault();
            setFilter("q", query.trim());
          }}
        >
          <div className="relative min-w-0">
            <Search className="pointer-events-none absolute left-3 top-2.5 h-4 w-4 text-muted-foreground" />
            <Input
              className="pl-9"
              value={query}
              onChange={(event) => setQuery(event.target.value)}
              placeholder="Search artist name or ID"
              aria-label="Search artist name or ID"
            />
          </div>
          <Select value={sort} onChange={(event) => setFilter("sort", event.target.value)} aria-label="Sort artists">
            <option value="updated_desc">Recently updated</option>
            <option value="attention_desc">Needs attention</option>
            <option value="name_asc">Name</option>
            <option value="failed_desc">Most failed</option>
            <option value="pending_desc">Most pending</option>
          </Select>
          <Select value={updateState} onChange={(event) => setFilter("updateState", event.target.value)} aria-label="Filter by update state">
            <option value="">Any update</option>
            <option value="attention">Needs attention</option>
            <option value="available">New works</option>
            <option value="stale">Check due</option>
          </Select>
          <Select value={accountStatus} onChange={(event) => setFilter("accountStatus", event.target.value)} aria-label="Filter by account status">
            <option value="">Any account</option>
            <option value="available">Available</option>
            <option value="unavailable">Unavailable</option>
            <option value="unknown">Unknown</option>
          </Select>
          <Select value={selectedTag} onChange={(event) => setFilter("localTag", event.target.value)} aria-label="Filter by local tag">
            <option value="">All tags</option>
            {tags.data?.items.map((tag) => (
              <option key={tag.id} value={tag.name}>
                {tag.name}
              </option>
            ))}
          </Select>
          <Select value={fileState} onChange={(event) => setFilter("fileState", event.target.value)} aria-label="Filter by file state">
            <option value="">All files</option>
            <option value="failed">Has failed files</option>
            <option value="pending">Has pending files</option>
            <option value="downloaded">Fully downloaded</option>
          </Select>
          <Button type="submit">Search</Button>
        </form>

        <div className="flex items-center justify-between gap-3 px-1 text-sm text-muted-foreground">
          <span>{artists.data?.total ?? 0} artist(s)</span>
          <span>Showing {items.length}</span>
        </div>

        {artists.isLoading ? (
          <DataState title="Loading artists" variant="loading" />
        ) : artists.isError ? (
          <DataState title="Could not load artists" description={artists.error.message} variant="error" />
        ) : items.length === 0 ? (
          <DataState title="No artists found" description="Try another filter or start a download." />
        ) : (
          <>
            <section className="grid gap-3 sm:grid-cols-2 xl:grid-cols-3 2xl:grid-cols-4">
              {items.map((artist) => (
                <ArtistCard key={artist.id} artist={artist} jobState={artistJobs.get(artist.id)} />
              ))}
            </section>
            <Pagination
              total={artists.data.total}
              page={page}
              pageSize={pageSize}
              pageSizeOptions={[12, 24, 48, 96]}
              itemLabel="artists"
              onPageChange={setPage}
              onPageSizeChange={setPageSize}
            />
          </>
        )}
      </div>
    </>
  );
}

function ArtistCard({
  artist,
  jobState
}: {
  artist: ArtistSummary;
  jobState?: ArtistJobState;
}): JSX.Element {
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const { pushToast } = useToast();
  const [pendingAction, setPendingAction] = React.useState<ArtistRunningJob["type"] | null>(null);
  const sync = useMutation({
    mutationFn: () => syncArtist(artist.id),
    onSuccess: (response) => {
      pushToast({ title: "Sync queued", description: response.job_id, tone: "success" });
      void queryClient.invalidateQueries({ queryKey: ["jobs"] });
    },
    onError: (error) => pushToast({ title: "Sync failed", description: error.message, tone: "error" }),
    onSettled: () => setPendingAction(null)
  });
  const download = useMutation({
    mutationFn: () => createArtistDownloadJob(artist.id),
    onSuccess: (response) => {
      pushToast({ title: "Download queued", description: response.job_id, tone: "success" });
      void queryClient.invalidateQueries({ queryKey: ["jobs"] });
    },
    onError: (error) => pushToast({ title: "Download failed", description: error.message, tone: "error" }),
    onSettled: () => setPendingAction(null)
  });
  const retry = useMutation({
    mutationFn: () => retryFailedArtist(artist.id),
    onSuccess: (response) => {
      pushToast({ title: "Retry failed queued", description: response.job_id, tone: "success" });
      void queryClient.invalidateQueries({ queryKey: ["jobs"] });
    },
    onError: (error) => pushToast({ title: "Retry failed", description: error.message, tone: "error" }),
    onSettled: () => setPendingAction(null)
  });

  const pendingFiles = artist.remote_file_count + artist.pending_file_count;
  const isDownloading = pendingAction === "download" || Boolean(jobState?.download);
  const isSyncing = pendingAction === "sync" || Boolean(jobState?.sync);
  const isRetrying = pendingAction === "retry" || Boolean(jobState?.retry);

  return (
    <article
      className="group rounded-md border bg-card p-4 transition-colors hover:border-primary/40 hover:bg-muted/30"
      role="button"
      tabIndex={0}
      onClick={() => navigate(`/artists/${artist.id}`)}
      onKeyDown={(event) => {
        if (event.key === "Enter") {
          navigate(`/artists/${artist.id}`);
        }
      }}
    >
      <div className="flex items-start gap-3">
        <ArtistAvatar artist={artist} />
        <div className="min-w-0 flex-1">
          <div className="flex items-start justify-between gap-2">
            <div className="min-w-0">
              <h2 className="truncate text-sm font-semibold group-hover:text-primary">{artist.name}</h2>
              <p className="mt-1 text-xs text-muted-foreground">Pixiv {artist.id}</p>
            </div>
            <ArtistAttentionMark artist={artist} />
          </div>
          <div className="mt-3 flex flex-wrap gap-1.5">
            <Badge tone="muted">{artist.artwork_count.toLocaleString()} artworks</Badge>
            <Badge tone={pendingFiles ? "default" : "muted"}>{pendingFiles.toLocaleString()} pending</Badge>
            <Badge tone={artist.failed_file_count ? "danger" : "muted"}>{artist.failed_file_count.toLocaleString()} failed</Badge>
          </div>
        </div>
      </div>

      <div className="mt-4 flex min-h-6 flex-wrap gap-1.5">
        {artist.local_tags.slice(0, 3).map((tag) => (
          <Badge key={tag.id}>{tag.name}</Badge>
        ))}
        {artist.local_tags.length > 3 ? <Badge tone="muted">+{artist.local_tags.length - 3}</Badge> : null}
        {artist.local_tags.length === 0 ? <span className="text-xs text-muted-foreground">No local tags</span> : null}
      </div>

      <dl className="mt-4 grid grid-cols-2 gap-3 text-sm">
        <Detail label="Downloaded" value={artist.downloaded_file_count.toLocaleString()} />
        <Detail label="Last checked" value={formatDate(artist.last_checked_at)} />
      </dl>

      <div className="mt-4 flex items-center justify-between gap-2 border-t pt-3" onClick={(event) => event.stopPropagation()}>
        <div className="flex flex-wrap gap-1.5">
          {jobState ? <ArtistJobBadges state={jobState} /> : null}
        </div>
        <div className="flex items-center gap-1">
          <Button
            type="button"
            variant="outline"
            size="icon"
            className={actionIconClass()}
            title="Download new works"
            aria-label="Download new works"
            disabled={isDownloading}
            onClick={() => {
              setPendingAction("download");
              download.mutate();
            }}
          >
            <Download className={isDownloading ? "h-4 w-4 animate-pulse" : "h-4 w-4"} aria-hidden="true" />
          </Button>
          <Button
            type="button"
            variant="outline"
            size="icon"
            className={actionIconClass()}
            title="Sync artist"
            aria-label="Sync artist"
            disabled={isSyncing}
            onClick={() => {
              setPendingAction("sync");
              sync.mutate();
            }}
          >
            <RefreshCw className={isSyncing ? "h-4 w-4 animate-spin" : "h-4 w-4"} aria-hidden="true" />
          </Button>
          <Button
            type="button"
            variant="outline"
            size="icon"
            className={actionIconClass("warning")}
            title="Retry failed files"
            aria-label="Retry failed files"
            disabled={isRetrying || artist.failed_file_count === 0}
            onClick={() => {
              setPendingAction("retry");
              retry.mutate();
            }}
          >
            <RotateCcw className={isRetrying ? "h-4 w-4 animate-spin" : "h-4 w-4"} aria-hidden="true" />
          </Button>
          <Button type="button" variant="outline" size="icon" className={actionIconClass()} title="Open Pixiv profile" aria-label="Open Pixiv profile" asChild>
            <a href={artist.profile_url} target="_blank" rel="noreferrer">
              <ExternalLink className="h-4 w-4" aria-hidden="true" />
            </a>
          </Button>
        </div>
      </div>
    </article>
  );
}

function ArtistAvatar({ artist }: { artist: ArtistSummary }): JSX.Element {
  const [failed, setFailed] = React.useState(false);
  React.useEffect(() => {
    setFailed(false);
  }, [artist.id, artist.avatar_cached]);

  if (artist.avatar_cached && !failed) {
    return (
      <img
        src={`/api/artists/${artist.id}/avatar`}
        alt=""
        className="h-12 w-12 shrink-0 rounded-md border object-cover"
        loading="lazy"
        onError={() => setFailed(true)}
      />
    );
  }
  return (
    <div className="flex h-12 w-12 shrink-0 items-center justify-center rounded-md border bg-muted text-sm font-semibold text-muted-foreground">
      {artist.name.slice(0, 1).toUpperCase() || "A"}
    </div>
  );
}

function ArtistAttentionMark({ artist }: { artist: ArtistSummary }): JSX.Element | null {
  if (artist.account_status === "unavailable") {
    return (
      <Badge tone="danger" title={artist.account_status_reason ?? "Pixiv profile is unavailable."}>
        <AlertTriangle className="h-3 w-3" aria-hidden="true" />
        Unavailable
      </Badge>
    );
  }
  if (artist.failed_file_count > 0) {
    return <Badge tone="danger">{artist.failed_file_count.toLocaleString()} failed</Badge>;
  }
  if (artist.has_remote_update) {
    return <Badge>New works</Badge>;
  }
  if (artist.is_check_stale) {
    return <Badge tone="warning">Check due</Badge>;
  }
  return null;
}

function ArtistJobBadges({ state }: { state: ArtistJobState }): JSX.Element {
  const jobs = [state.sync, state.download, state.retry].filter(Boolean) as ArtistRunningJob[];
  return (
    <>
      {jobs.map((job) => (
        <Badge key={job.type} tone={job.status === "running" ? "default" : "warning"}>
          {job.status === "running" ? <RefreshCw className="h-3 w-3 animate-spin" aria-hidden="true" /> : null}
          {artistJobLabel(job)}
        </Badge>
      ))}
    </>
  );
}

function Detail({ label, value }: { label: string; value: string }): JSX.Element {
  return (
    <div>
      <dt className="text-xs uppercase text-muted-foreground">{label}</dt>
      <dd className="mt-1 truncate font-medium">{value}</dd>
    </div>
  );
}

function artistJobMap(jobs: Job[]): Map<string, ArtistJobState> {
  const result = new Map<string, ArtistJobState>();
  for (const job of jobs) {
    if (!job.input_user_id || !isActiveJobStatus(job.status)) {
      continue;
    }
    const type = artistRunningJobType(job);
    if (!type) {
      continue;
    }
    const current = result.get(job.input_user_id) ?? {};
    current[type] = { type, status: job.status };
    result.set(job.input_user_id, current);
  }
  return result;
}

function artistRunningJobType(job: Job): ArtistRunningJob["type"] | null {
  if (job.type === "sync_artist") {
    return "sync";
  }
  if (job.type === "retry_failed_artist" || job.type === "retry_failed") {
    return "retry";
  }
  if (job.input_user_id) {
    return "download";
  }
  return null;
}

function isActiveJobStatus(status: Job["status"]): boolean {
  return status === "inactive" || status === "queued" || status === "running";
}

function artistJobLabel(job: ArtistRunningJob): string {
  if (job.type === "retry") {
    return job.status === "running" ? "Retrying" : "Retry queued";
  }
  if (job.type === "sync") {
    return job.status === "running" ? "Syncing" : "Sync queued";
  }
  return job.status === "running" ? "Downloading" : "Download queued";
}

function createArtistDownloadJob(artistId: string): Promise<{ job_id: string; status: string }> {
  const request: DownloadCreateRequest = {
    user_id: artistId,
    artwork_id: null,
    mode: "artist",
    force_rescan: false,
    retry_failed: false,
    only_new_artworks: true
  };
  return createDownloadJob(request);
}
