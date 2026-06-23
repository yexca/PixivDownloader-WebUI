import * as React from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Play } from "lucide-react";

import { createDownloadJob, type DownloadMode } from "@/api/downloads";
import { getJob } from "@/api/jobs";
import { getSettings } from "@/api/settings";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Tabs } from "@/components/ui/tabs";
import { DataState } from "@/components/DataState";
import { JobProgress } from "@/components/JobProgress";
import { PageHeader } from "@/components/PageHeader";
import { useToast } from "@/components/ToastProvider";
import { useJobStream } from "@/hooks/useJobStream";

export function DownloadPage(): JSX.Element {
  const queryClient = useQueryClient();
  const { pushToast } = useToast();
  const [mode, setMode] = React.useState<DownloadMode>("artist");
  const [input, setInput] = React.useState("");
  const [forceRescan, setForceRescan] = React.useState(false);
  const [retryFailed, setRetryFailed] = React.useState(false);
  const [lastJobId, setLastJobId] = React.useState<string | null>(null);
  const [fieldError, setFieldError] = React.useState<string | null>(null);
  const settings = useQuery({ queryKey: ["settings"], queryFn: getSettings });
  const job = useQuery({
    queryKey: ["job", lastJobId],
    queryFn: () => getJob(lastJobId!),
    enabled: Boolean(lastJobId),
    refetchInterval: (query) => {
      const status = query.state.data?.status;
      return status === "queued" || status === "running" ? 2500 : false;
    }
  });
  const stream = useJobStream(lastJobId);
  const createMutation = useMutation({
    mutationFn: () =>
      createDownloadJob({
        user_id: mode === "artist" ? input.trim() : null,
        artwork_id: mode === "artwork" ? input.trim() : null,
        mode,
        force_rescan: forceRescan,
        retry_failed: retryFailed
      }),
    onSuccess: (response) => {
      setLastJobId(response.job_id);
      pushToast({ title: "Download job queued", description: response.job_id, tone: "success" });
      void queryClient.invalidateQueries({ queryKey: ["jobs"] });
    },
    onError: (error) => {
      pushToast({ title: "Download could not start", description: error.message, tone: "error" });
    }
  });

  const submit = (event: React.FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (!/^\d+$/.test(input.trim())) {
      setFieldError(`${mode === "artist" ? "User" : "Artwork"} ID must contain digits only.`);
      return;
    }
    setFieldError(null);
    createMutation.mutate();
  };

  return (
    <>
      <PageHeader title="Download" description="Queue downloads by Pixiv user ID or artwork ID." />
      <div className="grid gap-4 p-4 sm:p-6 xl:grid-cols-[minmax(0,440px)_1fr]">
        <form className="surface space-y-4 p-4" onSubmit={submit}>
          <div>
            <label className="mb-2 block text-sm font-medium">Input mode</label>
            <Tabs
              value={mode}
              onValueChange={(value) => {
                setMode(value);
                setInput("");
                setFieldError(null);
              }}
              items={[
                { value: "artist", label: "User ID" },
                { value: "artwork", label: "Artwork ID" }
              ]}
            />
          </div>

          <div>
            <label className="mb-2 block text-sm font-medium" htmlFor="download-input">
              {mode === "artist" ? "Pixiv user ID" : "Pixiv artwork ID"}
            </label>
            <Input
              id="download-input"
              inputMode="numeric"
              value={input}
              onChange={(event) => setInput(event.target.value)}
              placeholder={mode === "artist" ? "123456" : "987654321"}
              aria-invalid={Boolean(fieldError)}
            />
            {fieldError ? <p className="mt-2 text-sm text-destructive">{fieldError}</p> : null}
          </div>

          <div className="space-y-3 rounded-md border bg-muted/30 p-3">
            <label className="flex items-center gap-2 text-sm">
              <input
                type="checkbox"
                checked={forceRescan}
                onChange={(event) => setForceRescan(event.target.checked)}
              />
              Force rescan
            </label>
            <label className="flex items-center gap-2 text-sm">
              <input
                type="checkbox"
                checked={retryFailed}
                onChange={(event) => setRetryFailed(event.target.checked)}
              />
              Retry failed files
            </label>
            <label className="flex items-center gap-2 text-sm text-muted-foreground">
              <input type="checkbox" checked={settings.data?.skip_existing_files ?? true} readOnly />
              Skip existing files
            </label>
          </div>

          <Button type="submit" className="w-full" disabled={createMutation.isPending}>
            <Play className="h-4 w-4" aria-hidden="true" />
            Start Download
          </Button>
          {settings.isError ? (
            <p className="text-sm text-destructive">Settings could not be loaded: {settings.error.message}</p>
          ) : null}
        </form>

        <section>
          {lastJobId && job.data ? (
            <div className="space-y-4">
              <JobProgress job={job.data} message={stream.lastMessage?.message} />
              <div className="surface p-4">
                <h2 className="text-sm font-semibold">Recent Events</h2>
                {job.data.events.length === 0 ? (
                  <p className="mt-3 text-sm text-muted-foreground">No events recorded yet.</p>
                ) : (
                  <div className="mt-3 max-h-[420px] space-y-2 overflow-auto">
                    {job.data.events.map((event) => (
                      <div key={`${event.id}-${event.created_at}`} className="rounded-md border p-3 text-sm">
                        <p className="font-medium">{event.message}</p>
                        <p className="mt-1 text-xs text-muted-foreground">{event.level}</p>
                      </div>
                    ))}
                  </div>
                )}
              </div>
            </div>
          ) : job.isLoading ? (
            <DataState title="Loading job" variant="loading" />
          ) : job.isError ? (
            <DataState title="Could not load job" description={job.error.message} variant="error" />
          ) : (
            <DataState title="No job selected" description="The current job progress will appear here." />
          )}
        </section>
      </div>
    </>
  );
}
