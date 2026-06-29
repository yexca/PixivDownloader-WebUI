import type * as React from "react";

import { cn } from "@/lib/utils";

type BadgeProps = {
  children: React.ReactNode;
  tone?: "default" | "success" | "warning" | "danger" | "muted";
  className?: string;
} & React.HTMLAttributes<HTMLSpanElement>;

const tones = {
  default: "border-primary/25 bg-primary/10 text-primary",
  success: "status-success",
  warning: "status-warning",
  danger: "border-destructive/25 bg-destructive/10 text-destructive",
  muted: "border-border bg-muted text-muted-foreground"
};

export function Badge({ children, tone = "default", className, ...props }: BadgeProps): JSX.Element {
  return (
    <span
      {...props}
      className={cn(
        "inline-flex min-h-6 items-center rounded-md border px-2 py-0.5 text-xs font-medium",
        tones[tone],
        className
      )}
    >
      {children}
    </span>
  );
}
