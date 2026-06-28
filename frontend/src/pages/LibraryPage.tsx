import * as React from "react";
import { Link, useSearchParams } from "react-router-dom";
import { AlertTriangle, Check, ExternalLink, Info, Plus, RefreshCw, RotateCcw, Search, Trash2, X } from "lucide-react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import {
  deleteArtist,
  getArtist,
  listArtists,
  listLocalTags,
  retryFailedArtist,
  setArtistLocalTags,
  syncArtist,
  type ArtistDetail,
  type ArtistSummary
} from "@/api/artists";
import { listJobs, type Job } from "@/api/jobs";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Dialog } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Select } from "@/components/ui/select";
import { Tabs } from "@/components/ui/tabs";
import { DataState } from "@/components/DataState";
import { PageHeader } from "@/components/PageHeader";
import { Pagination } from "@/components/Pagination";
import { ScrollableTable } from "@/components/ScrollableTable";
import { useToast } from "@/components/ToastProvider";
import { formatDate } from "@/lib/utils";

export function LibraryPage(): JSX.Element {
  const [searchParams, setSearchParams] = useSearchParams();
  const submittedQuery = searchParams.get("q") ?? "";
  const selectedTag = searchParams.get("localTag") ?? "";
  const fileState = searchParams.get("fileState") ?? "";
  const tagState = searchParams.get("tagState") ?? "";
  const accountStatus = searchParams.get("accountStatus") ?? "";
  const updateState = searchParams.get("updateState") ?? "";
  const sort = searchParams.get("sort") ?? "updated_desc";
  const page = Math.max(1, Number(searchParams.get("page") || "1"));
  const pageSize = Math.max(1, Number(searchParams.get("pageSize") || "50"));
  const [selectedArtistId, setSelectedArtistId] = React.useState<string | null>(
    searchParams.get("artist")
  );
  const [query, setQuery] = React.useState(submittedQuery);
  const artists = useQuery({
    queryKey: [
      "artists",
      submittedQuery,
      selectedTag,
      fileState,
      tagState,
      accountStatus,
      updateState,
      sort,
      pageSize,
      page
    ],
    queryFn: () =>
      listArtists({
        q: submittedQuery || undefined,
        local_tag: selectedTag || undefined,
        file_state: fileState || undefined,
        tag_state: tagState || undefined,
        account_status: accountStatus || undefined,
        update_state: updateState || undefined,
        sort,
        limit: pageSize,
        offset: (page - 1) * pageSize
      })
  });
  const tags = useQuery({ queryKey: ["local-tags"], queryFn: listLocalTags });
  const activeJobs = useQuery({
    queryKey: ["jobs", "library-active", 100],
    queryFn: () => listJobs({ limit: 100 }),
    refetchInterval: 4000
  });
  const selectedArtist = useQuery({
    queryKey: ["artist", selectedArtistId],
    queryFn: () => getArtist(selectedArtistId!),
    enabled: Boolean(selectedArtistId)
  });
  React.useEffect(() => {
    setQuery(submittedQuery);
  }, [submittedQuery]);
  React.useEffect(() => {
    const artistId = searchParams.get("artist");
    if (artistId && artistId !== selectedArtistId) {
      setSelectedArtistId(artistId);
    }
    if (!artistId && selectedArtistId) {
      setSelectedArtistId(null);
    }
  }, [searchParams, selectedArtistId]);

  const setFilter = (key: string, value: string) => {
    const nextParams = new URLSearchParams(searchParams);
    if (value) {
      nextParams.set(key, value);
    } else {
      nextParams.delete(key);
    }
    nextParams.set("page", "1");
    nextParams.delete("artist");
    setSelectedArtistId(null);
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
    nextParams.delete("artist");
    setSelectedArtistId(null);
    setSearchParams(nextParams, { replace: true });
  };
  const selectArtist = (artist: ArtistSummary) => {
    setSelectedArtistId(artist.id);
    const nextParams = new URLSearchParams(searchParams);
    nextParams.set("artist", artist.id);
    setSearchParams(nextParams, { replace: true });
  };

  return (
    <>
      <PageHeader title="Library" description="Browse artists already known to the local database." />
      <div className="space-y-4 p-4 sm:p-6">
        <form
          className="surface flex flex-col gap-3 p-3 sm:flex-row"
          onSubmit={(event) => {
            event.preventDefault();
            setFilter("q", query.trim());
          }}
        >
          <div className="relative flex-1">
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
            <option value="id_asc">ID</option>
            <option value="failed_desc">Most failed</option>
            <option value="pending_desc">Most pending</option>
            <option value="checked_asc">Oldest checked</option>
            <option value="remote_checked_asc">Oldest remote check</option>
          </Select>
          <Select value={updateState} onChange={(event) => setFilter("updateState", event.target.value)} aria-label="Filter by update state">
            <option value="">Any update state</option>
            <option value="attention">Needs attention</option>
            <option value="available">Update available</option>
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
          <Select value={tagState} onChange={(event) => setFilter("tagState", event.target.value)} aria-label="Filter by tag state">
            <option value="">Any tag state</option>
            <option value="tagged">Tagged</option>
            <option value="untagged">Untagged</option>
          </Select>
          <Button type="submit">Search</Button>
        </form>

        <div className="grid gap-4 xl:grid-cols-[minmax(680px,1fr)_360px]">
          <section className="space-y-3">
            {artists.isLoading ? (
              <DataState title="Loading artists" variant="loading" />
            ) : artists.isError ? (
              <DataState title="Could not load artists" description={artists.error.message} variant="error" />
            ) : artists.data.items.length === 0 ? (
              <DataState title="No artists found" description="Downloaded or scanned artists will appear here." />
            ) : (
              <>
                <ArtistTable
                  artists={artists.data.items}
                  selectedArtistId={selectedArtistId}
                  artistJobs={artistJobMap(activeJobs.data?.items ?? [])}
                  onSelect={selectArtist}
                />
                <Pagination
                  total={artists.data.total}
                  page={page}
                  pageSize={pageSize}
                  onPageChange={setPage}
                  onPageSizeChange={setPageSize}
                />
              </>
            )}
          </section>
          <aside className="space-y-3 xl:sticky xl:top-4 xl:max-h-[calc(100vh-2rem)] xl:self-start">
            {selectedArtistId && selectedArtist.data ? (
              <ArtistDetailPanel
                artist={selectedArtist.data}
                jobState={artistJobMap(activeJobs.data?.items ?? []).get(selectedArtist.data.id)}
              />
            ) : selectedArtist.isLoading ? (
              <DataState title="Loading artist detail" variant="loading" />
            ) : selectedArtist.isError ? (
              <DataState title="Could not load artist" description={selectedArtist.error.message} variant="error" />
            ) : (
              <DataState title="Select an artist" description="Artist metadata, tags, and maintenance actions appear here." />
            )}
          </aside>
        </div>
      </div>
    </>
  );
}

function ArtistTable({
  artists,
  selectedArtistId,
  artistJobs,
  onSelect
}: {
  artists: ArtistSummary[];
  selectedArtistId: string | null;
  artistJobs: Map<string, ArtistJobState>;
  onSelect: (artist: ArtistSummary) => void;
}): JSX.Element {
  const queryClient = useQueryClient();
  const { pushToast } = useToast();
  const [pendingSyncArtistId, setPendingSyncArtistId] = React.useState<string | null>(null);
  const [pendingRetryArtistId, setPendingRetryArtistId] = React.useState<string | null>(null);
  const sync = useMutation({
    mutationFn: (artistId: string) => syncArtist(artistId),
    onSuccess: (response) => {
      pushToast({ title: "Sync queued", description: response.job_id, tone: "success" });
      void queryClient.invalidateQueries({ queryKey: ["jobs"] });
    },
    onError: (error) => {
      pushToast({ title: "Sync failed", description: error.message, tone: "error" });
    },
    onSettled: () => setPendingSyncArtistId(null)
  });
  const retryFailed = useMutation({
    mutationFn: (artistId: string) => retryFailedArtist(artistId),
    onSuccess: (response) => {
      pushToast({ title: "Retry queued", description: response.job_id, tone: "success" });
      void queryClient.invalidateQueries({ queryKey: ["jobs"] });
    },
    onError: (error) => pushToast({ title: "Retry failed", description: error.message, tone: "error" }),
    onSettled: () => setPendingRetryArtistId(null)
  });
  const remove = useMutation({
    mutationFn: (artistId: string) => deleteArtist(artistId),
    onSuccess: () => {
      pushToast({ title: "Artist removed", tone: "success" });
      void queryClient.invalidateQueries({ queryKey: ["artists"] });
      void queryClient.invalidateQueries({ queryKey: ["local-tags"] });
    },
    onError: (error) => pushToast({ title: "Remove failed", description: error.message, tone: "error" })
  });

  return (
    <ScrollableTable>
      <table className="data-table min-w-[760px]">
        <thead className="table-head">
          <tr>
            <th className="sticky-col-left px-3 py-2">Artist</th>
            <th className="px-3 py-2">Files</th>
            <th className="px-3 py-2">Attention</th>
            <th className="px-3 py-2">Tags</th>
            <th className="px-3 py-2">Last checked</th>
            <th className="sticky-col-right px-3 py-2">Actions</th>
          </tr>
        </thead>
        <tbody>
          {artists.map((artist) => {
            const selected = selectedArtistId === artist.id;
            const jobState = artistJobs.get(artist.id);
            const isSyncing = pendingSyncArtistId === artist.id || Boolean(jobState?.sync);
            const isRetrying = pendingRetryArtistId === artist.id || Boolean(jobState?.retry);
            return (
            <tr
              key={artist.id}
              className="cursor-pointer hover:bg-muted/40"
              data-selected={selected ? "true" : "false"}
              onClick={() => onSelect(artist)}
            >
              <td className="table-cell sticky-col-left min-w-52 max-w-72">
                <div className="flex items-center gap-3">
                  <ArtistAvatar artist={artist} size="sm" />
                  <div className="min-w-0">
                    <div className="truncate font-medium">{artist.name}</div>
                    <div className="text-xs text-muted-foreground">Pixiv {artist.id}</div>
                    {jobState ? <ArtistJobBadges state={jobState} compact /> : null}
                  </div>
                </div>
              </td>
              <td className="table-cell">
                <FileSummary artist={artist} />
              </td>
              <td className="table-cell">
                <ArtistStatusBadges artist={artist} compact />
              </td>
              <td className="table-cell">
                <TagPreview artist={artist} />
              </td>
              <td className="table-cell">{formatDate(artist.last_checked_at)}</td>
              <td className="table-cell sticky-col-right min-w-44">
                <div className="flex items-center gap-1">
                  <Button
                    type="button"
                    variant="outline"
                    size="icon"
                    title="Sync artist"
                    aria-label="Sync artist"
                    disabled={isSyncing}
                    onClick={(event) => {
                      event.stopPropagation();
                      setPendingSyncArtistId(artist.id);
                      sync.mutate(artist.id);
                    }}
                  >
                    <RefreshCw className={isSyncing ? "h-4 w-4 animate-spin" : "h-4 w-4"} aria-hidden="true" />
                  </Button>
                  <Button
                    type="button"
                    variant="outline"
                    size="icon"
                    title="Retry failed files"
                    aria-label="Retry failed files"
                    disabled={isRetrying || artist.failed_file_count === 0}
                    onClick={(event) => {
                      event.stopPropagation();
                      setPendingRetryArtistId(artist.id);
                      retryFailed.mutate(artist.id);
                    }}
                  >
                    <RotateCcw className={isRetrying ? "h-4 w-4 animate-spin" : "h-4 w-4"} aria-hidden="true" />
                  </Button>
                  <Button
                    type="button"
                    variant={selected ? "secondary" : "ghost"}
                    size="icon"
                    title="Show artist details"
                    aria-label="Show artist details"
                    onClick={(event) => {
                      event.stopPropagation();
                      onSelect(artist);
                    }}
                  >
                    <Info className="h-4 w-4" aria-hidden="true" />
                  </Button>
                  <Button type="button" variant="ghost" size="icon" title="Open Pixiv profile" aria-label="Open Pixiv profile" asChild>
                    <a href={artist.profile_url} target="_blank" rel="noreferrer" onClick={(event) => event.stopPropagation()}>
                      <ExternalLink className="h-4 w-4" aria-hidden="true" />
                    </a>
                  </Button>
                </div>
              </td>
            </tr>
          );
          })}
        </tbody>
      </table>
    </ScrollableTable>
  );
}

type ArtistDetailTab = "overview" | "details" | "tags";
type ArtistRunningJob = {
  type: "sync" | "download" | "retry";
  status: Job["status"];
};
type ArtistJobState = Partial<Record<ArtistRunningJob["type"], ArtistRunningJob>>;

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

function isActiveJobStatus(status: Job["status"]): boolean {
  return status === "inactive" || status === "queued" || status === "running";
}

function artistRunningJobType(job: Job): ArtistRunningJob["type"] | null {
  if (job.type === "sync_artist") {
    return "sync";
  }
  if (job.type === "retry_failed_artist" || job.type === "retry_failed") {
    return "retry";
  }
  if (job.type === "download_artist" || job.type === "rescan_artist") {
    return "download";
  }
  return null;
}

function ArtistDetailPanel({
  artist,
  jobState
}: {
  artist: ArtistDetail;
  jobState?: ArtistJobState;
}): JSX.Element {
  const [activeTab, setActiveTab] = React.useState<ArtistDetailTab>("overview");
  const queryClient = useQueryClient();
  const { pushToast } = useToast();
  const [syncPending, setSyncPending] = React.useState(false);
  const [retryPending, setRetryPending] = React.useState(false);
  const [removeDialogOpen, setRemoveDialogOpen] = React.useState(false);
  const isSyncing = syncPending || Boolean(jobState?.sync);
  const isRetrying = retryPending || Boolean(jobState?.retry);
  const sync = useMutation({
    mutationFn: () => syncArtist(artist.id),
    onSuccess: (response) => {
      pushToast({ title: "Sync queued", description: response.job_id, tone: "success" });
      void queryClient.invalidateQueries({ queryKey: ["jobs"] });
    },
    onError: (error) => pushToast({ title: "Sync failed", description: error.message, tone: "error" }),
    onSettled: () => setSyncPending(false)
  });
  const retryFailed = useMutation({
    mutationFn: () => retryFailedArtist(artist.id),
    onSuccess: (response) => {
      pushToast({ title: "Retry queued", description: response.job_id, tone: "success" });
      void queryClient.invalidateQueries({ queryKey: ["jobs"] });
    },
    onError: (error) => pushToast({ title: "Retry failed", description: error.message, tone: "error" }),
    onSettled: () => setRetryPending(false)
  });
  const remove = useMutation({
    mutationFn: () => deleteArtist(artist.id),
    onSuccess: () => {
      pushToast({ title: "Artist removed", tone: "success" });
      void queryClient.invalidateQueries({ queryKey: ["artists"] });
      void queryClient.invalidateQueries({ queryKey: ["local-tags"] });
      setRemoveDialogOpen(false);
    },
    onError: (error) => pushToast({ title: "Remove failed", description: error.message, tone: "error" })
  });

  React.useEffect(() => {
    setActiveTab("overview");
  }, [artist.id]);

  return (
    <>
      <div className="surface flex max-h-[calc(100vh-2rem)] flex-col p-4">
      <div className="shrink-0">
        <div className="flex items-start gap-3">
          <ArtistAvatar artist={artist} size="lg" />
          <div className="min-w-0 flex-1">
            <h2 className="truncate text-sm font-semibold">{artist.name}</h2>
            <p className="mt-1 text-xs text-muted-foreground">Pixiv user {artist.id}</p>
            <div className="mt-2">
              <ArtistStatusBadges artist={artist} />
            </div>
            {jobState ? (
              <div className="mt-2">
                <ArtistJobBadges state={jobState} />
              </div>
            ) : null}
          </div>
        </div>
        <div className="mt-4 flex flex-wrap gap-2">
          <Button
            type="button"
            variant="outline"
            size="sm"
            onClick={() => {
              setSyncPending(true);
              sync.mutate();
            }}
            disabled={isSyncing}
          >
            <RefreshCw className={isSyncing ? "h-4 w-4 animate-spin" : "h-4 w-4"} aria-hidden="true" />
            Sync
          </Button>
          <Button
            type="button"
            variant="outline"
            size="sm"
            onClick={() => {
              setRetryPending(true);
              retryFailed.mutate();
            }}
            disabled={isRetrying || artist.failed_file_count === 0}
          >
            <RotateCcw className={isRetrying ? "h-4 w-4 animate-spin" : "h-4 w-4"} aria-hidden="true" />
            Retry
          </Button>
          <Button type="button" variant="ghost" size="sm" asChild>
            <a href={artist.profile_url} target="_blank" rel="noreferrer">
              <ExternalLink className="h-4 w-4" aria-hidden="true" />
              Pixiv
            </a>
          </Button>
          <Button type="button" variant="ghost" size="sm" asChild>
            <Link to={`/artists/${artist.id}`}>Artworks</Link>
          </Button>
          <Button
            type="button"
            variant="ghost"
            size="icon"
            title="Remove from library"
            aria-label="Remove from library"
            disabled={remove.isPending}
            onClick={() => setRemoveDialogOpen(true)}
          >
            <Trash2 className="h-4 w-4" aria-hidden="true" />
          </Button>
        </div>
        <Tabs<ArtistDetailTab>
          value={activeTab}
          onValueChange={setActiveTab}
          className="mt-4"
          items={[
            { value: "overview", label: "Overview" },
            { value: "details", label: "Details" },
            { value: "tags", label: "Tags" }
          ]}
        />
      </div>
      <div className="mt-4 min-h-0 flex-1 overflow-auto pr-1">
        {activeTab === "overview" ? <ArtistOverview artist={artist} /> : null}
        {activeTab === "details" ? <ArtistFullDetails artist={artist} /> : null}
        {activeTab === "tags" ? <ArtistTagsPanel artist={artist} /> : null}
      </div>
      </div>
      <RemoveArtistConfirmDialog
        artist={artist}
        open={removeDialogOpen}
        isRemoving={remove.isPending}
        onOpenChange={setRemoveDialogOpen}
        onConfirm={() => remove.mutate()}
      />
    </>
  );
}

function RemoveArtistConfirmDialog({
  artist,
  open,
  isRemoving,
  onOpenChange,
  onConfirm
}: {
  artist: ArtistDetail;
  open: boolean;
  isRemoving: boolean;
  onOpenChange: (open: boolean) => void;
  onConfirm: () => void;
}): JSX.Element {
  return (
    <Dialog
      open={open}
      title="Remove artist"
      description={`${artist.name} will be removed from the local library. Local files will not be deleted.`}
      onOpenChange={onOpenChange}
      footer={
        <>
          <Button type="button" variant="outline" disabled={isRemoving} onClick={() => onOpenChange(false)}>
            Cancel
          </Button>
          <Button type="button" variant="destructive" disabled={isRemoving} onClick={onConfirm}>
            <Trash2 className="h-4 w-4" aria-hidden="true" />
            Remove
          </Button>
        </>
      }
    />
  );
}

function ArtistOverview({ artist }: { artist: ArtistDetail }): JSX.Element {
  return (
    <div className="space-y-4">
      <div className="grid grid-cols-2 gap-3">
        <Metric label="Artworks" value={artist.artwork_count} />
        <Metric label="Downloaded" value={artist.downloaded_file_count} />
        <Metric label="Remote" value={artist.remote_file_count + artist.pending_file_count} />
        <Metric label="Failed" value={artist.failed_file_count} tone={artist.failed_file_count > 0 ? "danger" : "normal"} />
      </div>
      {artist.account_status_reason ? (
        <p className="rounded-md border border-destructive/20 bg-destructive/10 p-3 text-sm text-destructive">
          {artist.account_status_reason}
        </p>
      ) : null}
      <dl className="grid grid-cols-2 gap-3 text-sm">
        <Detail label="Last checked" value={formatDate(artist.last_checked_at)} />
        <Detail label="Remote checked" value={formatDate(artist.remote_latest_checked_at)} />
        <Detail label="Latest ID" value={artist.latest_downloaded_artwork_id ?? "-"} />
        <Detail label="Remote latest" value={artist.remote_latest_artwork_id ?? "-"} />
      </dl>
    </div>
  );
}

function ArtistFullDetails({ artist }: { artist: ArtistDetail }): JSX.Element {
  return (
    <div className="space-y-4">
      <dl className="grid grid-cols-2 gap-3 text-sm">
        <Detail label="Pixiv ID" value={artist.id} />
        <Detail label="Account" value={artist.account ?? "-"} />
        <Detail label="Status" value={artist.account_status} />
        <Detail label="Account checked" value={formatDate(artist.account_status_checked_at)} />
        <Detail label="Latest downloaded" value={artist.latest_downloaded_artwork_id ?? "-"} />
        <Detail label="Remote latest" value={artist.remote_latest_artwork_id ?? "-"} />
        <Detail label="Last checked" value={formatDate(artist.last_checked_at)} />
        <Detail label="Stale threshold" value={`${artist.check_stale_days} days`} />
      </dl>
      {artist.comment ? <p className="whitespace-pre-wrap rounded-md border p-3 text-sm text-muted-foreground">{artist.comment}</p> : null}
      <section>
        <h3 className="text-sm font-semibold">Name History</h3>
        {artist.name_history.length === 0 ? (
          <p className="mt-2 text-sm text-muted-foreground">No previous names recorded.</p>
        ) : (
          <div className="mt-3 space-y-2">
            {artist.name_history.map((item) => (
              <div key={item.id} className="rounded-md border p-3 text-sm">
                <div className="font-medium">{item.name}</div>
                <div className="mt-1 text-xs text-muted-foreground">
                  {formatDate(item.first_seen_at)} - {formatDate(item.last_seen_at)}
                </div>
              </div>
            ))}
          </div>
        )}
      </section>
    </div>
  );
}

function ArtistTagsPanel({ artist }: { artist: ArtistDetail }): JSX.Element {
  return (
    <div className="space-y-3">
      <h3 className="text-sm font-semibold">Local Tags</h3>
      <TagEditor artist={artist} />
    </div>
  );
}

function ArtistAvatar({ artist, size }: { artist: ArtistSummary; size: "sm" | "lg" }): JSX.Element {
  const [failed, setFailed] = React.useState(false);
  React.useEffect(() => {
    setFailed(false);
  }, [artist.id, artist.avatar_cached]);

  const className =
    size === "lg"
      ? "h-12 w-12 text-sm"
      : "h-9 w-9 text-xs";
  if (artist.avatar_cached && !failed) {
    return (
      <img
        src={`/api/artists/${artist.id}/avatar`}
        alt=""
        className={`${className} shrink-0 rounded-md border object-cover`}
        loading="lazy"
        onError={() => setFailed(true)}
      />
    );
  }
  return (
    <div className={`${className} flex shrink-0 items-center justify-center rounded-md border bg-muted font-semibold text-muted-foreground`}>
      {artist.name.slice(0, 1).toUpperCase() || "A"}
    </div>
  );
}

function Metric({
  label,
  value,
  tone = "normal"
}: {
  label: string;
  value: number;
  tone?: "normal" | "danger";
}): JSX.Element {
  return (
    <div className="rounded-md border bg-muted/25 p-3">
      <p className="text-xs font-medium uppercase text-muted-foreground">{label}</p>
      <p className={tone === "danger" ? "mt-2 text-xl font-semibold text-destructive" : "mt-2 text-xl font-semibold"}>
        {value.toLocaleString()}
      </p>
    </div>
  );
}

function Detail({ label, value }: { label: string; value: string }): JSX.Element {
  return (
    <div>
      <dt className="text-xs uppercase text-muted-foreground">{label}</dt>
      <dd className="mt-1 break-words font-medium">{value}</dd>
    </div>
  );
}

function FileSummary({ artist }: { artist: ArtistSummary }): JSX.Element {
  const remote = artist.remote_file_count + artist.pending_file_count;
  return (
    <div className="min-w-48 space-y-1 text-sm">
      <div className="font-medium">{artist.downloaded_file_count.toLocaleString()} downloaded</div>
      <div className="flex flex-wrap gap-1">
        <Badge tone="muted">{artist.artwork_count.toLocaleString()} artworks</Badge>
        <Badge tone="default">{remote.toLocaleString()} remote</Badge>
        <Badge tone={artist.failed_file_count > 0 ? "danger" : "muted"}>{artist.failed_file_count.toLocaleString()} failed</Badge>
      </div>
    </div>
  );
}

function TagPreview({ artist }: { artist: ArtistSummary }): JSX.Element {
  if (artist.local_tags.length === 0) {
    return <span className="text-sm text-muted-foreground">-</span>;
  }
  const visibleTags = artist.local_tags.slice(0, 2);
  const hiddenCount = artist.local_tags.length - visibleTags.length;
  return (
    <div className="flex min-w-36 flex-wrap gap-1.5">
      {visibleTags.map((tag) => (
        <Badge key={tag.id}>{tag.name}</Badge>
      ))}
      {hiddenCount > 0 ? <Badge tone="muted">+{hiddenCount}</Badge> : null}
    </div>
  );
}

function ArtistStatusBadges({ artist, compact = false }: { artist: ArtistSummary; compact?: boolean }): JSX.Element {
  const badges: JSX.Element[] = [];
  if (artist.account_status === "unavailable") {
    badges.push(
      <Badge key="unavailable" tone="danger" title={artist.account_status_reason ?? "Pixiv profile is unavailable."}>
        <AlertTriangle className="h-3 w-3" aria-hidden="true" />
        Unavailable
      </Badge>
    );
  } else if (artist.account_status === "available") {
    badges.push(
      <Badge key="available" tone="success">
        Available
      </Badge>
    );
  } else {
    badges.push(
      <Badge key="unknown" tone="muted">
        Unknown
      </Badge>
    );
  }
  if (artist.has_remote_update) {
    badges.push(
      <Badge key="update" tone="default">
        Update
      </Badge>
    );
  }
  if (artist.is_check_stale) {
    badges.push(
      <Badge key="stale" tone="warning">
        Check due
      </Badge>
    );
  }
  if (compact && badges.length === 1 && artist.account_status === "available") {
    return <span className="text-sm text-muted-foreground">Healthy</span>;
  }
  return <div className={compact ? "flex min-w-44 flex-wrap gap-1.5" : "flex flex-wrap gap-1.5"}>{badges}</div>;
}

function ArtistJobBadges({
  state,
  compact = false
}: {
  state: ArtistJobState;
  compact?: boolean;
}): JSX.Element {
  const jobs = [state.sync, state.download, state.retry].filter(Boolean) as ArtistRunningJob[];
  if (jobs.length === 0) {
    return <></>;
  }
  return (
    <div className={compact ? "mt-1 flex flex-wrap gap-1" : "flex flex-wrap gap-1.5"}>
      {jobs.map((job) => (
        <Badge key={job.type} tone={job.status === "running" ? "default" : "warning"} title={artistJobTitle(job)}>
          {job.status === "running" ? (
            <RefreshCw className="h-3 w-3 animate-spin" aria-hidden="true" />
          ) : null}
          {artistJobLabel(job, compact)}
        </Badge>
      ))}
    </div>
  );
}

function artistJobLabel(job: ArtistRunningJob, compact: boolean): string {
  const labels = {
    sync: "Sync",
    download: "Download",
    retry: "Retry"
  };
  if (compact) {
    return labels[job.type];
  }
  if (job.status === "inactive") {
    return `${labels[job.type]} waiting`;
  }
  if (job.status === "queued") {
    return `${labels[job.type]} queued`;
  }
  return `${labels[job.type]} running`;
}

function artistJobTitle(job: ArtistRunningJob): string {
  if (job.status === "inactive") {
    return "Waiting for workflow capacity.";
  }
  if (job.status === "queued") {
    return "Queued for the download worker.";
  }
  return "Currently running.";
}

function TagEditor({ artist }: { artist: ArtistSummary }): JSX.Element {
  const [draft, setDraft] = React.useState("");
  const [isAdding, setIsAdding] = React.useState(false);
  const queryClient = useQueryClient();
  const { pushToast } = useToast();
  const save = useMutation({
    mutationFn: (tags: string[]) => setArtistLocalTags(artist.id, tags),
    onSuccess: () => {
      setDraft("");
      setIsAdding(false);
      pushToast({ title: "Tags saved", tone: "success" });
      void queryClient.invalidateQueries({ queryKey: ["artists"] });
      void queryClient.invalidateQueries({ queryKey: ["local-tags"] });
    },
    onError: (error) => pushToast({ title: "Tags failed", description: error.message, tone: "error" })
  });

  React.useEffect(() => {
    setDraft("");
    setIsAdding(false);
  }, [artist.id]);

  const tagNames = artist.local_tags.map((tag) => tag.name);
  const trimmedDraft = draft.trim();
  const canAdd =
    trimmedDraft.length > 0 &&
    !tagNames.some((tagName) => tagName.toLocaleLowerCase() === trimmedDraft.toLocaleLowerCase());

  const addTag = () => {
    if (!canAdd) {
      return;
    }
    save.mutate([...tagNames, trimmedDraft]);
  };

  const removeTag = (tagName: string) => {
    save.mutate(tagNames.filter((name) => name !== tagName));
  };

  return (
    <div className="flex min-w-[240px] flex-wrap items-center gap-1.5">
      {artist.local_tags.map((tag) => (
        <Badge key={tag.id} tone="default" className="gap-1 pr-1">
          {tag.name}
          <button
            type="button"
            className="inline-flex h-4 w-4 items-center justify-center rounded-sm text-primary hover:bg-primary/10"
            aria-label={`Remove ${tag.name}`}
            disabled={save.isPending}
            onClick={() => removeTag(tag.name)}
          >
            <X className="h-3 w-3" aria-hidden="true" />
          </button>
        </Badge>
      ))}

      {isAdding ? (
        <span className="inline-flex min-h-6 items-center gap-1 rounded-md border border-primary/25 bg-primary/10 px-1 py-0.5 text-xs font-medium text-primary">
          <input
            className="h-5 w-24 bg-transparent px-1 text-xs outline-none placeholder:text-primary/60"
            value={draft}
            onChange={(event) => setDraft(event.target.value)}
            onKeyDown={(event) => {
              if (event.key === "Enter") {
                event.preventDefault();
                addTag();
              }
              if (event.key === "Escape") {
                setDraft("");
                setIsAdding(false);
              }
            }}
            placeholder="Tag"
            autoFocus
            aria-label={`New local tag for ${artist.name}`}
          />
          <button
            type="button"
            className="inline-flex h-4 w-4 items-center justify-center rounded-sm hover:bg-primary/10 disabled:opacity-50"
            disabled={save.isPending || !canAdd}
            aria-label="Save tag"
            onClick={addTag}
          >
            <Check className="h-3 w-3" aria-hidden="true" />
          </button>
          <button
            type="button"
            className="inline-flex h-4 w-4 items-center justify-center rounded-sm hover:bg-primary/10"
            disabled={save.isPending}
            aria-label="Cancel tag"
            onClick={() => {
              setDraft("");
              setIsAdding(false);
            }}
          >
            <X className="h-3 w-3" aria-hidden="true" />
          </button>
        </span>
      ) : (
        <button
          type="button"
          className="inline-flex h-6 min-w-6 items-center justify-center rounded-md border border-dashed border-border bg-background px-1 text-muted-foreground hover:border-primary/50 hover:text-primary"
          disabled={save.isPending}
          aria-label={`Add local tag for ${artist.name}`}
          onClick={() => setIsAdding(true)}
        >
          <Plus className="h-3.5 w-3.5" aria-hidden="true" />
        </button>
      )}
    </div>
  );
}
