import { Link } from "react-router-dom";

import type { Job } from "@/api/jobs";
import { StatusBadge } from "@/components/StatusBadge";
import { Button } from "@/components/ui/button";
import { Progress } from "@/components/ui/progress";
import { formatDate, percent } from "@/lib/utils";

type JobTableProps = {
  jobs: Job[];
  onSelect?: (job: Job) => void;
};

export function JobTable({ jobs, onSelect }: JobTableProps): JSX.Element {
  return (
    <div className="overflow-x-auto rounded-md border bg-card">
      <table className="w-full min-w-[760px] border-collapse">
        <thead className="table-head">
          <tr>
            <th className="px-3 py-2">Job</th>
            <th className="px-3 py-2">Input</th>
            <th className="px-3 py-2">Status</th>
            <th className="px-3 py-2">Progress</th>
            <th className="px-3 py-2">Created</th>
            <th className="px-3 py-2">Action</th>
          </tr>
        </thead>
        <tbody>
          {jobs.map((job) => {
            const done = job.completed_files + job.skipped_files + job.failed_files;
            return (
              <tr key={job.id} className="hover:bg-muted/40">
                <td className="table-cell">
                  <div className="font-medium">{job.type.replaceAll("_", " ")}</div>
                  <div className="text-xs text-muted-foreground">{job.id}</div>
                </td>
                <td className="table-cell">
                  {job.input_user_id ? (
                    <Link className="text-primary hover:underline" to={`/artists/${job.input_user_id}`}>
                      User {job.input_user_id}
                    </Link>
                  ) : (
                    `Artwork ${job.input_artwork_id ?? "-"}`
                  )}
                </td>
                <td className="table-cell">
                  <StatusBadge status={job.status} />
                </td>
                <td className="table-cell w-52">
                  <Progress value={percent(done, job.total_files)} />
                  <div className="mt-1 text-xs text-muted-foreground">
                    {done}/{job.total_files || "-"}
                  </div>
                </td>
                <td className="table-cell">{formatDate(job.created_at)}</td>
                <td className="table-cell">
                  <Button type="button" variant="outline" size="sm" onClick={() => onSelect?.(job)}>
                    Details
                  </Button>
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}
