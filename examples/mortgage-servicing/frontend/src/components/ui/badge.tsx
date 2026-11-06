import { cn } from "@/lib/utils";

const tones = {
  neutral: "bg-muted text-muted-foreground",
  brand: "bg-primary-soft text-primary",
  success: "bg-success-soft text-success",
  warning: "bg-warning-soft text-warning",
  danger: "bg-danger-soft text-danger",
} as const;

export type BadgeTone = keyof typeof tones;

export function Badge({
  tone = "neutral",
  className,
  ...props
}: React.HTMLAttributes<HTMLSpanElement> & { tone?: BadgeTone }) {
  return (
    <span
      className={cn(
        "inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-xs font-medium capitalize",
        tones[tone],
        className,
      )}
      {...props}
    />
  );
}

/** Tone for a mortgage / draft status word. */
export function statusTone(status: string): BadgeTone {
  const s = status.toLowerCase();
  if (["active", "committed", "verified", "paid"].includes(s)) return "success";
  if (["draft", "pending", "pending_approval"].includes(s)) return "warning";
  if (["closed"].includes(s)) return "neutral";
  if (["failed", "rejected", "late"].includes(s)) return "danger";
  return "brand";
}
