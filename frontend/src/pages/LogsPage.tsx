import * as React from "react";
import { RefreshCw } from "lucide-react";
import { useQuery } from "@tanstack/react-query";

import { getRecentLogs } from "@/api/logs";
import { Button } from "@/components/ui/button";
import { Select } from "@/components/ui/select";
import { Badge } from "@/components/ui/badge";
import { DataState } from "@/components/DataState";
import { PageHeader } from "@/components/PageHeader";
import { formatDate } from "@/lib/utils";

export function LogsPage(): JSX.Element {
  const [level, setLevel] = React.useState("");
  const logs = useQuery({
    queryKey: ["logs", 200],
    queryFn: () => getRecentLogs(200),
    refetchInterval: 5000
  });
  const items = logs.data?.filter((event) => !level || event.level === level) ?? [];

  return (
    <>
      <PageHeader
        title="Logs"
        description="Recent job events for troubleshooting downloads."
        actions={
          <>
            <Select value={level} onChange={(event) => setLevel(event.target.value)} aria-label="Filter log level">
              <option value="">All levels</option>
              <option value="debug">Debug</option>
              <option value="info">Info</option>
              <option value="warning">Warning</option>
              <option value="error">Error</option>
            </Select>
            <Button type="button" variant="outline" onClick={() => void logs.refetch()} disabled={logs.isFetching}>
              <RefreshCw className="h-4 w-4" aria-hidden="true" />
              Refresh
            </Button>
          </>
        }
      />
      <div className="p-4 sm:p-6">
        {logs.isLoading ? (
          <DataState title="Loading logs" variant="loading" />
        ) : logs.isError ? (
          <DataState title="Could not load logs" description={logs.error.message} variant="error" />
        ) : items.length === 0 ? (
          <DataState title="No log events" description="Job activity and failures will appear here." />
        ) : (
          <div className="overflow-x-auto rounded-md border bg-card">
            <table className="w-full min-w-[760px] border-collapse">
              <thead className="table-head">
                <tr>
                  <th className="px-3 py-2">Time</th>
                  <th className="px-3 py-2">Level</th>
                  <th className="px-3 py-2">Message</th>
                  <th className="px-3 py-2">Job</th>
                </tr>
              </thead>
              <tbody>
                {items.map((event) => (
                  <tr key={`${event.id}-${event.created_at}`} className="hover:bg-muted/40">
                    <td className="table-cell">{formatDate(event.created_at)}</td>
                    <td className="table-cell">
                      <Badge tone={event.level === "error" ? "danger" : event.level === "warning" ? "warning" : "muted"}>
                        {event.level}
                      </Badge>
                    </td>
                    <td className="table-cell">{event.message}</td>
                    <td className="table-cell break-all text-xs text-muted-foreground">{event.job_id}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </>
  );
}
