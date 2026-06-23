import * as React from "react";
import { useQueryClient } from "@tanstack/react-query";

import { websocketUrl } from "@/api/client";
import type { JobDetail, JobListResponse, JobStreamMessage } from "@/api/jobs";

type UseJobStreamResult = {
  connected: boolean;
  lastMessage: JobStreamMessage | null;
};

const terminalStatuses = new Set(["completed", "failed", "cancelled"]);

export function useJobStream(jobId: string | null | undefined): UseJobStreamResult {
  const queryClient = useQueryClient();
  const [connected, setConnected] = React.useState(false);
  const [lastMessage, setLastMessage] = React.useState<JobStreamMessage | null>(null);
  const lastStatusRef = React.useRef<string | null>(null);

  React.useEffect(() => {
    if (!jobId) {
      return;
    }

    let socket: WebSocket | null = null;
    let reconnectTimer: number | null = null;
    let attempts = 0;
    let closedByHook = false;

    const connect = () => {
      socket = new WebSocket(websocketUrl(`/jobs/${jobId}/stream`));

      socket.onopen = () => {
        attempts = 0;
        setConnected(true);
      };

      socket.onmessage = (event) => {
        const message = JSON.parse(event.data as string) as JobStreamMessage;
        lastStatusRef.current = message.status;
        setLastMessage(message);
        queryClient.setQueryData<JobDetail>(["job", jobId], (current) =>
          current
            ? {
                ...current,
                status: message.status,
                total_files: message.total_files,
                completed_files: message.completed_files,
                skipped_files: message.skipped_files,
                failed_files: message.failed_files
              }
            : current
        );
        queryClient.setQueryData<JobListResponse>(["jobs", "all", 50], (current) =>
          current
            ? {
                ...current,
                items: current.items.map((job) =>
                  job.id === jobId
                    ? {
                        ...job,
                        status: message.status,
                        total_files: message.total_files,
                        completed_files: message.completed_files,
                        skipped_files: message.skipped_files,
                        failed_files: message.failed_files
                      }
                    : job
                )
              }
            : current
        );
        void queryClient.invalidateQueries({ queryKey: ["logs"] });
        if (terminalStatuses.has(message.status)) {
          void queryClient.invalidateQueries({ queryKey: ["job", jobId] });
          void queryClient.invalidateQueries({ queryKey: ["jobs"] });
        }
      };

      socket.onclose = () => {
        setConnected(false);
        if (!closedByHook && !terminalStatuses.has(lastStatusRef.current ?? "")) {
          attempts += 1;
          reconnectTimer = window.setTimeout(connect, Math.min(5000, 500 * attempts));
        }
      };

      socket.onerror = () => {
        socket?.close();
      };
    };

    connect();

    return () => {
      closedByHook = true;
      setConnected(false);
      if (reconnectTimer) {
        window.clearTimeout(reconnectTimer);
      }
      socket?.close();
    };
  }, [jobId, queryClient]);

  return { connected, lastMessage };
}
