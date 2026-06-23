import { XCircle } from "lucide-react";
import { useMutation, useQueryClient } from "@tanstack/react-query";

import { cancelJob, type Job } from "@/api/jobs";
import { Button } from "@/components/ui/button";
import { Progress } from "@/components/ui/progress";
import { StatusBadge } from "@/components/StatusBadge";
import { useToast } from "@/components/ToastProvider";
import { isCancellable, percent } from "@/lib/utils";

type JobProgressProps = {
  job: Job;
  message?: string | null;
};

export function JobProgress({ job, message }: JobProgressProps): JSX.Element {
  const queryClient = useQueryClient();
  const { pushToast } = useToast();
  const done = job.completed_files + job.skipped_files + job.failed_files;
  const value = percent(done, job.total_files);
  const mutation = useMutation({
    mutationFn: () => cancelJob(job.id),
    onSuccess: () => {
      pushToast({ title: "Cancellation requested", tone: "success" });
      void queryClient.invalidateQueries({ queryKey: ["jobs"] });
      void queryClient.invalidateQueries({ queryKey: ["job", job.id] });
    },
    onError: (error) => {
      pushToast({ title: "Cancel failed", description: error.message, tone: "error" });
    }
  });

  return (
    <div className="surface p-4">
      <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
        <div className="min-w-0">
          <div className="flex flex-wrap items-center gap-2">
            <h2 className="truncate text-sm font-semibold">{job.type.replaceAll("_", " ")}</h2>
            <StatusBadge status={job.status} />
          </div>
          <p className="mt-1 text-sm text-muted-foreground">
            {job.input_user_id ? `User ID ${job.input_user_id}` : `Artwork ID ${job.input_artwork_id ?? "-"}`}
          </p>
        </div>
        {isCancellable(job.status) ? (
          <Button
            type="button"
            variant="outline"
            size="sm"
            disabled={mutation.isPending || job.cancel_requested}
            onClick={() => mutation.mutate()}
          >
            <XCircle className="h-4 w-4" aria-hidden="true" />
            Cancel
          </Button>
        ) : null}
      </div>
      <div className="mt-4 space-y-2">
        <Progress value={value} />
        <div className="flex flex-wrap justify-between gap-2 text-xs text-muted-foreground">
          <span>{value}% complete</span>
          <span>
            {job.completed_files} downloaded, {job.skipped_files} skipped, {job.failed_files} failed
            {job.total_files ? ` of ${job.total_files}` : ""}
          </span>
        </div>
      </div>
      {message ? <p className="mt-3 text-sm text-muted-foreground">{message}</p> : null}
      {job.error_message ? <p className="mt-3 text-sm text-destructive">{job.error_message}</p> : null}
    </div>
  );
}
