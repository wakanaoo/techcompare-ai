interface SpinnerProps {
  size?: "sm" | "lg";
  label?: string;
}

/**
 * CSSアニメーションのみの軽量スピナー。「処理中である」ことを視覚的に示す。
 * label を渡すとスクリーンリーダー向けに状態を伝える(視覚的には非表示)。
 */
export function Spinner({ size = "sm", label }: SpinnerProps) {
  const className = size === "lg" ? "spinner spinner--lg" : "spinner";
  return (
    <span className={className} role="status" aria-live="polite">
      {label && <span style={{ position: "absolute", width: 1, height: 1, overflow: "hidden" }}>{label}</span>}
    </span>
  );
}
