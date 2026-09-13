import type { ReactNode } from "react";

interface PageContainerProps {
  children: ReactNode;
  /** ページごとに最適な最大幅(px)。フォーム画面は狭め、表を含む画面は広め、等。 */
  maxWidth?: number;
}

/**
 * 各ページで重複していた `<main style={{ maxWidth, margin: "0 auto", padding }}>` を
 * 共通化しただけの薄いラッパー。
 */
export function PageContainer({ children, maxWidth = 640 }: PageContainerProps) {
  return (
    <main className="page-container" style={{ maxWidth }}>
      {children}
    </main>
  );
}
