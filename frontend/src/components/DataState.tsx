import { AlertTriangle, Inbox, Loader2 } from "lucide-react";

import { Button } from "@/components/ui/button";

type DataStateProps = {
  title: string;
  description?: string;
  actionLabel?: string;
  onAction?: () => void;
  variant?: "loading" | "empty" | "error";
};

export function DataState({
  title,
  description,
  actionLabel,
  onAction,
  variant = "empty"
}: DataStateProps): JSX.Element {
  const Icon = variant === "loading" ? Loader2 : variant === "error" ? AlertTriangle : Inbox;
  return (
    <div className="flex min-h-40 flex-col items-center justify-center gap-3 rounded-md border border-dashed bg-card p-6 text-center">
      <Icon
        className={variant === "loading" ? "h-6 w-6 animate-spin text-primary" : "h-6 w-6 text-muted-foreground"}
        aria-hidden="true"
      />
      <div>
        <p className="text-sm font-medium">{title}</p>
        {description ? <p className="mt-1 text-sm text-muted-foreground">{description}</p> : null}
      </div>
      {actionLabel && onAction ? (
        <Button type="button" variant="outline" size="sm" onClick={onAction}>
          {actionLabel}
        </Button>
      ) : null}
    </div>
  );
}
