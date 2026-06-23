import { Badge } from "@/components/ui/badge";
import type { JobStatus } from "@/api/jobs";

type StatusBadgeProps = {
  status: JobStatus | string;
};

export function StatusBadge({ status }: StatusBadgeProps): JSX.Element {
  const tone =
    status === "completed"
      ? "success"
      : status === "failed"
        ? "danger"
        : status === "cancelled"
          ? "muted"
          : status === "running"
            ? "default"
            : "warning";

  return <Badge tone={tone}>{status}</Badge>;
}
