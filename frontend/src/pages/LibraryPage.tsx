import * as React from "react";
import { Link } from "react-router-dom";
import { Check, ExternalLink, Plus, RefreshCw, RotateCcw, Search, Trash2, X } from "lucide-react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import {
  createArtist,
  deleteArtist,
  listArtists,
  listLocalTags,
  retryFailedArtist,
  setArtistLocalTags,
  syncArtist,
  type ArtistSummary
} from "@/api/artists";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Select } from "@/components/ui/select";
import { DataState } from "@/components/DataState";
import { PageHeader } from "@/components/PageHeader";
import { useToast } from "@/components/ToastProvider";
import { formatDate } from "@/lib/utils";

export function LibraryPage(): JSX.Element {
  const [query, setQuery] = React.useState("");
  const [submittedQuery, setSubmittedQuery] = React.useState("");
  const [selectedTag, setSelectedTag] = React.useState("");
  const [newArtistId, setNewArtistId] = React.useState("");
  const [sort, setSort] = React.useState("updated_desc");
  const queryClient = useQueryClient();
  const { pushToast } = useToast();
  const artists = useQuery({
    queryKey: ["artists", submittedQuery, selectedTag, sort],
    queryFn: () =>
      listArtists({
        q: submittedQuery || undefined,
        local_tag: selectedTag || undefined,
        sort,
        limit: 100
      })
  });
  const tags = useQuery({ queryKey: ["local-tags"], queryFn: listLocalTags });
  const addArtist = useMutation({
    mutationFn: (userId: string) => createArtist(userId),
    onSuccess: (response) => {
      setNewArtistId("");
      pushToast({ title: "Sync queued", description: response.job_id, tone: "success" });
      void queryClient.invalidateQueries({ queryKey: ["jobs"] });
    },
    onError: (error) => pushToast({ title: "Artist could not be added", description: error.message, tone: "error" })
  });

  return (
    <>
      <PageHeader title="Library" description="Browse artists already known to the local database." />
      <div className="space-y-4 p-4 sm:p-6">
        <form
          className="surface flex flex-col gap-3 p-3 sm:flex-row"
          onSubmit={(event) => {
            event.preventDefault();
            const userId = newArtistId.trim();
            if (!/^\d+$/.test(userId)) {
              pushToast({ title: "Invalid user ID", description: "Pixiv user ID must contain digits only.", tone: "error" });
              return;
            }
            addArtist.mutate(userId);
          }}
        >
          <Input
            value={newArtistId}
            onChange={(event) => setNewArtistId(event.target.value)}
            placeholder="Pixiv user ID"
            inputMode="numeric"
            aria-label="Pixiv user ID"
          />
          <Button type="submit" disabled={addArtist.isPending}>
            <Plus className="h-4 w-4" aria-hidden="true" />
            Add Artist
          </Button>
        </form>

        <form
          className="surface flex flex-col gap-3 p-3 sm:flex-row"
          onSubmit={(event) => {
            event.preventDefault();
            setSubmittedQuery(query.trim());
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
          <Select value={sort} onChange={(event) => setSort(event.target.value)} aria-label="Sort artists">
            <option value="updated_desc">Recently updated</option>
            <option value="name_asc">Name</option>
            <option value="id_asc">ID</option>
          </Select>
          <Select value={selectedTag} onChange={(event) => setSelectedTag(event.target.value)} aria-label="Filter by local tag">
            <option value="">All tags</option>
            {tags.data?.items.map((tag) => (
              <option key={tag.id} value={tag.name}>
                {tag.name}
              </option>
            ))}
          </Select>
          <Button type="submit">Search</Button>
        </form>

        {artists.isLoading ? (
          <DataState title="Loading artists" variant="loading" />
        ) : artists.isError ? (
          <DataState title="Could not load artists" description={artists.error.message} variant="error" />
        ) : artists.data.items.length === 0 ? (
          <DataState title="No artists found" description="Downloaded or scanned artists will appear here." />
        ) : (
          <ArtistTable artists={artists.data.items} />
        )}
      </div>
    </>
  );
}

function ArtistTable({ artists }: { artists: ArtistSummary[] }): JSX.Element {
  const queryClient = useQueryClient();
  const { pushToast } = useToast();
  const sync = useMutation({
    mutationFn: (artistId: string) => syncArtist(artistId),
    onSuccess: (response) => {
      pushToast({ title: "Sync queued", description: response.job_id, tone: "success" });
      void queryClient.invalidateQueries({ queryKey: ["jobs"] });
    },
    onError: (error) => {
      pushToast({ title: "Sync failed", description: error.message, tone: "error" });
    }
  });
  const retryFailed = useMutation({
    mutationFn: (artistId: string) => retryFailedArtist(artistId),
    onSuccess: (response) => {
      pushToast({ title: "Retry queued", description: response.job_id, tone: "success" });
      void queryClient.invalidateQueries({ queryKey: ["jobs"] });
    },
    onError: (error) => pushToast({ title: "Retry failed", description: error.message, tone: "error" })
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
    <div className="overflow-x-auto rounded-md border bg-card">
      <table className="w-full min-w-[1140px] border-collapse">
        <thead className="table-head">
          <tr>
            <th className="px-3 py-2">Artist</th>
            <th className="px-3 py-2">ID</th>
            <th className="px-3 py-2">Artworks</th>
            <th className="px-3 py-2">Files</th>
            <th className="px-3 py-2">Remote</th>
            <th className="px-3 py-2">Failed</th>
            <th className="px-3 py-2">Latest ID</th>
            <th className="px-3 py-2">Tags</th>
            <th className="px-3 py-2">Last checked</th>
            <th className="px-3 py-2">Actions</th>
          </tr>
        </thead>
        <tbody>
          {artists.map((artist) => (
            <tr key={artist.id} className="hover:bg-muted/40">
              <td className="table-cell">
                <Link to={`/artists/${artist.id}`} className="font-medium text-primary hover:underline">
                  {artist.name}
                </Link>
              </td>
              <td className="table-cell">{artist.id}</td>
              <td className="table-cell">{artist.artwork_count}</td>
              <td className="table-cell">{artist.downloaded_file_count}</td>
              <td className="table-cell">{artist.remote_file_count + artist.pending_file_count}</td>
              <td className="table-cell">{artist.failed_file_count}</td>
              <td className="table-cell">{artist.latest_downloaded_artwork_id ?? "None"}</td>
              <td className="table-cell">
                <TagEditor artist={artist} />
              </td>
              <td className="table-cell">{formatDate(artist.last_checked_at)}</td>
              <td className="table-cell">
                <div className="flex flex-wrap items-center gap-2">
                  <Button
                    type="button"
                    variant="outline"
                    size="sm"
                    disabled={sync.isPending}
                    onClick={() => sync.mutate(artist.id)}
                  >
                    <RefreshCw className="h-4 w-4" aria-hidden="true" />
                    Sync
                  </Button>
                  <Button
                    type="button"
                    variant="outline"
                    size="sm"
                    disabled={retryFailed.isPending || artist.failed_file_count === 0}
                    onClick={() => retryFailed.mutate(artist.id)}
                  >
                    <RotateCcw className="h-4 w-4" aria-hidden="true" />
                    Retry
                  </Button>
                  <Button type="button" variant="ghost" size="icon" title="Open Pixiv profile" aria-label="Open Pixiv profile" asChild>
                    <a href={artist.profile_url} target="_blank" rel="noreferrer">
                      <ExternalLink className="h-4 w-4" aria-hidden="true" />
                    </a>
                  </Button>
                  <Button
                    type="button"
                    variant="ghost"
                    size="icon"
                    title="Remove from library"
                    aria-label="Remove from library"
                    disabled={remove.isPending}
                    onClick={() => {
                      if (window.confirm(`Remove ${artist.name} from the local library? Local files will not be deleted.`)) {
                        remove.mutate(artist.id);
                      }
                    }}
                  >
                    <Trash2 className="h-4 w-4" aria-hidden="true" />
                  </Button>
                </div>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
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
