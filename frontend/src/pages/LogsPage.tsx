import * as React from "react";
import { useSearchParams } from "react-router-dom";
import { RefreshCw } from "lucide-react";
import { useQuery } from "@tanstack/react-query";

import { getRecentLogs } from "@/api/logs";
import { Button } from "@/components/ui/button";
import { Select } from "@/components/ui/select";
import { Badge } from "@/components/ui/badge";
import { DataState } from "@/components/DataState";
import { PageHeader } from "@/components/PageHeader";
import { Pagination } from "@/components/Pagination";
import { ScrollableTable } from "@/components/ScrollableTable";
import { formatDate } from "@/lib/utils";

export function LogsPage(): JSX.Element {
  const [searchParams, setSearchParams] = useSearchParams();
  const level = searchParams.get("level") ?? "";
  const page = Math.max(1, Number(searchParams.get("page") || "1"));
  const pageSize = Math.max(1, Number(searchParams.get("pageSize") || "50"));
  const logs = useQuery({
    queryKey: ["logs", level, pageSize, page],
    queryFn: () => getRecentLogs({ level: level || undefined, limit: pageSize, offset: (page - 1) * pageSize }),
    refetchInterval: 5000
  });
  const items = logs.data?.items ?? [];
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

  return (
    <>
      <PageHeader
        title="Logs"
        description="Recent job events for troubleshooting downloads."
        actions={
          <>
            <Select value={level} onChange={(event) => setFilter("level", event.target.value)} aria-label="Filter log level">
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
      <div className="space-y-3 p-4 sm:p-6">
        {logs.isLoading ? (
          <DataState title="Loading logs" variant="loading" />
        ) : logs.isError ? (
          <DataState title="Could not load logs" description={logs.error.message} variant="error" />
        ) : items.length === 0 ? (
          <DataState title="No log events" description="Job activity and failures will appear here." />
        ) : (
          <>
            <ScrollableTable>
              <table className="data-table min-w-[760px]">
                <thead className="table-head">
                  <tr>
                    <th className="sticky-col-left px-3 py-2">Time</th>
                    <th className="px-3 py-2">Level</th>
                    <th className="px-3 py-2">Message</th>
                    <th className="sticky-col-right px-3 py-2">Job</th>
                  </tr>
                </thead>
                <tbody>
                  {items.map((event) => (
                    <tr key={`${event.id}-${event.created_at}`} className="hover:bg-muted/40">
                      <td className="table-cell sticky-col-left min-w-44">{formatDate(event.created_at)}</td>
                      <td className="table-cell">
                        <Badge tone={event.level === "error" ? "danger" : event.level === "warning" ? "warning" : "muted"}>
                          {event.level}
                        </Badge>
                      </td>
                      <td className="table-cell min-w-80">{event.message}</td>
                      <td className="table-cell sticky-col-right max-w-56 break-all text-xs text-muted-foreground">{event.job_id}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </ScrollableTable>
            <Pagination
              total={logs.data.total}
              page={page}
              pageSize={pageSize}
              onPageChange={setPage}
              onPageSizeChange={setPageSize}
            />
          </>
        )}
      </div>
    </>
  );
}
