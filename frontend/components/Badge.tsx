import type { ReactNode } from "react";

type BadgeTone = "neutral" | "info" | "success" | "danger";

interface BadgeProps {
  tone?: BadgeTone;
  children: ReactNode;
}

export function Badge({ tone = "neutral", children }: BadgeProps) {
  return <span className={`badge badge--${tone}`}>{children}</span>;
}
