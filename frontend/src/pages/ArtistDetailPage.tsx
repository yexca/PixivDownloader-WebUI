import { useParams, useSearchParams } from "react-router-dom";
import { ExternalLink, RefreshCw, RotateCcw } from "lucide-react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { getArtist, listArtistArtworks, listArtworkFiles, retryArtworkFile, type ArtworkSummary } from "@/api/artists";
import { createDownloadJob } from "@/api/downloads";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { DataState } from "@/components/DataState";
import { PageHeader } from "@/components/PageHeader";
import { Pagination } from "@/components/Pagination";
import { ScrollableTable } from "@/components/ScrollableTable";
import { useToast } from "@/components/ToastProvider";
import { formatDate } from "@/lib/utils";

export function ArtistDetailPage(): JSX.Element {
  const { artistId } = useParams();
  const [searchParams, setSearchParams] = useSearchParams();
  const page = Math.max(1, Number(searchParams.get("page") || "1"));
  const pageSize = Math.max(1, Number(searchParams.get("pageSize") || "50"));
  const queryClient = useQueryClient();
  const { pushToast } = useToast();
  const artist = useQuery({
    queryKey: ["artist", artistId],
    queryFn: () => getArtist(artistId!),
    enabled: Boolean(artistId)
  });
  const artworks = useQuery({
    queryKey: ["artist-artworks", artistId, pageSize, page],
    queryFn: () => listArtistArtworks(artistId!, pageSize, (page - 1) * pageSize),
    enabled: Boolean(artistId)
  });
  const rescan = useMutation({
    mutationFn: () =>
      createDownloadJob({
        user_id: artistId!,
        artwork_id: null,
        mode: "artist",
        force_rescan: true,
        retry_failed: false
      }),
    onSuccess: (response) => {
      pushToast({ title: "Rescan queued", description: response.job_id, tone: "success" });
      void queryClient.invalidateQueries({ queryKey: ["jobs"] });
    },
    onError: (error) => pushToast({ title: "Rescan failed", description: error.message, tone: "error" })
  });

  if (!artistId) {
    return <DataState title="Artist ID is missing" variant="error" />;
  }
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

  return (
    <>
      <PageHeader
        title={artist.data?.name ?? "Artist Detail"}
        description={artist.data ? `Pixiv user ${artist.data.id}` : "Loading artist metadata."}
        actions={
          artist.data ? (
            <>
              <Button type="button" variant="outline" onClick={() => rescan.mutate()} disabled={rescan.isPending}>
                <RefreshCw className="h-4 w-4" aria-hidden="true" />
                Rescan
              </Button>
              <Button type="button" variant="ghost" asChild>
                <a href={artist.data.profile_url} target="_blank" rel="noreferrer">
                  <ExternalLink className="h-4 w-4" aria-hidden="true" />
                  Pixiv
                </a>
              </Button>
            </>
          ) : null
        }
      />
      <div className="space-y-4 p-4 sm:p-6">
        {artist.isLoading ? (
          <DataState title="Loading artist" variant="loading" />
        ) : artist.isError ? (
          <DataState title="Could not load artist" description={artist.error.message} variant="error" />
        ) : (
          <div className="grid gap-3 sm:grid-cols-3">
            <Metric label="Artworks" value={artist.data.artwork_count} />
            <Metric label="Downloaded files" value={artist.data.downloaded_file_count} />
            <Metric label="Failed files" value={artist.data.failed_file_count} />
          </div>
        )}

        <section className="space-y-3">
          <h2 className="text-sm font-semibold">Artworks</h2>
          {artworks.isLoading ? (
            <DataState title="Loading artworks" variant="loading" />
          ) : artworks.isError ? (
            <DataState title="Could not load artworks" description={artworks.error.message} variant="error" />
          ) : artworks.data.items.length === 0 ? (
            <DataState title="No artworks recorded" description="Run a rescan to discover artworks." />
          ) : (
            <>
              <ArtworkTable artworks={artworks.data.items} />
              <Pagination
                total={artworks.data.total}
                page={page}
                pageSize={pageSize}
                onPageChange={setPage}
                onPageSizeChange={setPageSize}
              />
            </>
          )}
        </section>
      </div>
    </>
  );
}

function Metric({ label, value }: { label: string; value: number }): JSX.Element {
  return (
    <div className="surface p-4">
      <p className="text-xs font-medium uppercase text-muted-foreground">{label}</p>
      <p className="mt-2 text-2xl font-semibold">{value.toLocaleString()}</p>
    </div>
  );
}

function ArtworkTable({ artworks }: { artworks: ArtworkSummary[] }): JSX.Element {
  return (
    <ScrollableTable>
      <table className="data-table min-w-[860px]">
        <thead className="table-head">
          <tr>
            <th className="sticky-col-left px-3 py-2">Artwork</th>
            <th className="px-3 py-2">Pages</th>
            <th className="px-3 py-2">Files</th>
            <th className="px-3 py-2">Failed</th>
            <th className="px-3 py-2">Pixiv date</th>
            <th className="sticky-col-right px-3 py-2">Files</th>
          </tr>
        </thead>
        <tbody>
          {artworks.map((artwork) => (
            <ArtworkRow key={artwork.id} artwork={artwork} />
          ))}
        </tbody>
      </table>
    </ScrollableTable>
  );
}

function ArtworkRow({ artwork }: { artwork: ArtworkSummary }): JSX.Element {
  const files = useQuery({
    queryKey: ["artwork-files", artwork.id],
    queryFn: () => listArtworkFiles(artwork.id),
    enabled: artwork.failed_files > 0
  });
  const { pushToast } = useToast();
  const queryClient = useQueryClient();
  const retry = useMutation({
    mutationFn: (fileId: number) => retryArtworkFile(fileId),
    onSuccess: (response) => {
      pushToast({ title: "Retry queued", description: response.job_id, tone: "success" });
      void queryClient.invalidateQueries({ queryKey: ["jobs"] });
    },
    onError: (error) => pushToast({ title: "Retry failed", description: error.message, tone: "error" })
  });

  return (
    <tr className="hover:bg-muted/40">
      <td className="table-cell sticky-col-left min-w-64 max-w-96">
        <div className="font-medium">{artwork.title || "Untitled"}</div>
        <div className="text-xs text-muted-foreground">{artwork.id}</div>
      </td>
      <td className="table-cell">{artwork.page_count}</td>
      <td className="table-cell">
        <div className="flex flex-wrap gap-1">
          <Badge tone="success">{artwork.downloaded_files} downloaded</Badge>
          <Badge tone="muted">{artwork.skipped_files} skipped</Badge>
        </div>
      </td>
      <td className="table-cell sticky-col-right min-w-32">
        <Badge tone={artwork.failed_files > 0 ? "danger" : "muted"}>{artwork.failed_files}</Badge>
      </td>
      <td className="table-cell">{formatDate(artwork.pixiv_created_at)}</td>
      <td className="table-cell">
        {artwork.failed_files > 0 && files.data?.items.find((file) => file.id !== null && file.status === "failed") ? (
          <Button
            type="button"
            variant="outline"
            size="sm"
            disabled={retry.isPending}
            onClick={() => {
              const file = files.data?.items.find((item) => item.id !== null && item.status === "failed");
              if (file?.id) {
                retry.mutate(file.id);
              }
            }}
          >
            <RotateCcw className="h-4 w-4" aria-hidden="true" />
            Retry
          </Button>
        ) : (
          <a
            className="text-sm text-primary hover:underline"
            href={`https://www.pixiv.net/artworks/${artwork.id}`}
            target="_blank"
            rel="noreferrer"
          >
            Open Pixiv
          </a>
        )}
      </td>
    </tr>
  );
}
