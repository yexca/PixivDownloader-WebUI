import { clsx, type ClassValue } from "clsx";
import { twMerge } from "tailwind-merge";

export function cn(...inputs: ClassValue[]): string {
  return twMerge(clsx(inputs));
}

export function formatDate(value?: string | null): string {
  if (!value) {
    return "-";
  }
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) {
    return value;
  }
  return new Intl.DateTimeFormat(undefined, {
    dateStyle: "medium",
    timeStyle: "short"
  }).format(date);
}

export function percent(completed: number, total: number): number {
  if (total <= 0) {
    return 0;
  }
  return Math.min(100, Math.round((completed / total) * 100));
}

export function isCancellable(status: string): boolean {
  return status === "inactive" || status === "queued" || status === "running";
}

export function isRetryable(status: string): boolean {
  return status === "failed";
}

export function isRerunnable(status: string): boolean {
  return status === "completed" || status === "failed" || status === "cancelled";
}
