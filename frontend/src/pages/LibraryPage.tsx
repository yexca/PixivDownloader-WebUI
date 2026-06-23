import * as React from "react";
import { Link } from "react-router-dom";
import { ExternalLink, RefreshCw, Search } from "lucide-react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { listArtists, type ArtistSummary } from "@/api/artists";
import { createDownloadJob } from "@/api/downloads";
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
  const [sort, setSort] = React.useState("updated_desc");
  const artists = useQuery({
    queryKey: ["artists", submittedQuery, sort],
    queryFn: () => listArtists({ q: submittedQuery || undefined, sort, limit: 100 })
  });

  return (
    <>
      <PageHeader title="Library" description="Browse artists already known to the local database." />
      <div className="space-y-4 p-4 sm:p-6">
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
  const rescan = useMutation({
    mutationFn: (artistId: string) =>
      createDownloadJob({
        user_id: artistId,
        artwork_id: null,
        mode: "artist",
        force_rescan: true,
        retry_failed: false
      }),
    onSuccess: (response) => {
      pushToast({ title: "Rescan queued", description: response.job_id, tone: "success" });
      void queryClient.invalidateQueries({ queryKey: ["jobs"] });
    },
    onError: (error) => {
      pushToast({ title: "Rescan failed", description: error.message, tone: "error" });
    }
  });

  return (
    <div className="overflow-x-auto rounded-md border bg-card">
      <table className="w-full min-w-[820px] border-collapse">
        <thead className="table-head">
          <tr>
            <th className="px-3 py-2">Artist</th>
            <th className="px-3 py-2">ID</th>
            <th className="px-3 py-2">Artworks</th>
            <th className="px-3 py-2">Files</th>
            <th className="px-3 py-2">Failed</th>
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
              <td className="table-cell">{artist.failed_file_count}</td>
              <td className="table-cell">{formatDate(artist.last_checked_at)}</td>
              <td className="table-cell">
                <div className="flex items-center gap-2">
                  <Button
                    type="button"
                    variant="outline"
                    size="sm"
                    disabled={rescan.isPending}
                    onClick={() => rescan.mutate(artist.id)}
                  >
                    <RefreshCw className="h-4 w-4" aria-hidden="true" />
                    Rescan
                  </Button>
                  <Button type="button" variant="ghost" size="icon" title="Open Pixiv profile" aria-label="Open Pixiv profile" asChild>
                    <a href={artist.profile_url} target="_blank" rel="noreferrer">
                      <ExternalLink className="h-4 w-4" aria-hidden="true" />
                    </a>
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
