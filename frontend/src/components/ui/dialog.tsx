import * as React from "react";
import { X } from "lucide-react";

import { cn } from "@/lib/utils";
import { Button } from "@/components/ui/button";

type DialogProps = {
  open: boolean;
  title: string;
  description?: string;
  children?: React.ReactNode;
  footer?: React.ReactNode;
  onOpenChange: (open: boolean) => void;
};

export function Dialog({
  open,
  title,
  description,
  children,
  footer,
  onOpenChange
}: DialogProps): JSX.Element | null {
  React.useEffect(() => {
    if (!open) {
      return;
    }
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        onOpenChange(false);
      }
    };
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [onOpenChange, open]);

  if (!open) {
    return null;
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4">
      <button
        type="button"
        aria-label="Close dialog"
        className="absolute inset-0 bg-foreground/30"
        onClick={() => onOpenChange(false)}
      />
      <section
        role="dialog"
        aria-modal="true"
        aria-labelledby="app-dialog-title"
        aria-describedby={description ? "app-dialog-description" : undefined}
        className="surface relative z-10 w-full max-w-lg p-4 shadow-lg"
      >
        <div className="flex items-start justify-between gap-4">
          <div className="min-w-0">
            <h2 id="app-dialog-title" className="text-base font-semibold leading-6">
              {title}
            </h2>
            {description ? (
              <p id="app-dialog-description" className="mt-1 text-sm leading-6 text-muted-foreground">
                {description}
              </p>
            ) : null}
          </div>
          <Button type="button" variant="ghost" size="icon" aria-label="Close" onClick={() => onOpenChange(false)}>
            <X className="h-4 w-4" aria-hidden="true" />
          </Button>
        </div>
        {children ? <div className="mt-4">{children}</div> : null}
        {footer ? <div className={cn("mt-5 flex flex-wrap justify-end gap-2")}>{footer}</div> : null}
      </section>
    </div>
  );
}
