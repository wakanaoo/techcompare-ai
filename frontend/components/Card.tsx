import type { CSSProperties, ReactNode } from "react";

interface CardProps {
  children: ReactNode;
  style?: CSSProperties;
  className?: string;
  id?: string;
}

export function Card({ children, style, className, id }: CardProps) {
  const classes = className ? `card ${className}` : "card";
  return (
    <div id={id} className={classes} style={style}>
      {children}
    </div>
  );
}
