import type { CSSProperties, ReactNode } from "react";

interface CardProps {
  children: ReactNode;
  style?: CSSProperties;
  className?: string;
}

export function Card({ children, style, className }: CardProps) {
  const classes = className ? `card ${className}` : "card";
  return (
    <div className={classes} style={style}>
      {children}
    </div>
  );
}
