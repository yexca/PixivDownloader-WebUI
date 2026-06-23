import type * as React from "react";

import { cn } from "@/lib/utils";

type BadgeProps = {
  children: React.ReactNode;
  tone?: "default" | "success" | "warning" | "danger" | "muted";
  className?: string;
};

const tones = {
  default: "border-primary/25 bg-primary/10 text-primary",
  success: "border-emerald-500/25 bg-emerald-50 text-emerald-700",
  warning: "border-amber-500/25 bg-amber-50 text-amber-700",
  danger: "border-destructive/25 bg-destructive/10 text-destructive",
  muted: "border-border bg-muted text-muted-foreground"
};

export function Badge({ children, tone = "default", className }: BadgeProps): JSX.Element {
  return (
    <span
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
