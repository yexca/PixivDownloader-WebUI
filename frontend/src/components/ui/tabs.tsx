import { cn } from "@/lib/utils";

type TabsProps<T extends string> = {
  value: T;
  onValueChange: (value: T) => void;
  items: Array<{ value: T; label: string }>;
  className?: string;
};

export function Tabs<T extends string>({
  value,
  onValueChange,
  items,
  className
}: TabsProps<T>): JSX.Element {
  return (
    <div className={cn("inline-flex rounded-md border bg-muted p-1", className)} role="tablist">
      {items.map((item) => (
        <button
          key={item.value}
          type="button"
          role="tab"
          aria-selected={value === item.value}
          className={cn(
            "h-8 rounded-sm px-3 text-sm font-medium text-muted-foreground transition-colors",
            value === item.value && "bg-background text-foreground shadow-sm"
          )}
          onClick={() => onValueChange(item.value)}
        >
          {item.label}
        </button>
      ))}
    </div>
  );
}
