"use client";

import { useEffect, useId, useRef, useState, type KeyboardEvent, type ReactNode } from "react";

/** SSR時はwindow.matchMediaが無いため、常に「hoverあり(PC)」として初期化する。 */
function detectNoHover(): boolean {
  if (typeof window === "undefined" || !window.matchMedia) return false;
  return window.matchMedia("(hover: none)").matches;
}

interface InfoTooltipProps {
  /**
   * トリガーの中身。省略時は小さな"ⓘ"アイコン(Base Point chip内に併設する
   * 独立したinfoボタン用)。ConceptPopoverのように、用語名自体をトリガーに
   * したい場合はここに用語名のテキストを渡す。
   */
  children?: ReactNode;
  /** スクリーンリーダー向けのトリガーのaria-label。 */
  triggerLabel: string;
  description: string;
  className?: string;
}

/**
 * Base Point / Concept共通の説明表示コンポーネント(Phase 5C Finishing)。
 *
 * PC(hoverあり): トリガーへのhover/focusで表示し、mouseleave/blurで隠れる。
 * タッチ端末(hoverなし、`(hover: none)`で判定): tapで開閉をtoggleし、
 * 外側tapまたはEscapeで閉じる。どちらのモードでもEscapeで閉じられる。
 *
 * Base Point chip(選択トグルの責務を持つ既存button)の中に置く場合は、
 * この内部の<button>とchip本体のbuttonが入れ子にならないよう、呼び出し側で
 * 兄弟要素として並べること(HTMLはbutton内buttonを許可しないため)。
 */
export function InfoTooltip({ children, triggerLabel, description, className }: InfoTooltipProps) {
  const [open, setOpen] = useState(false);
  // 初回render時点で判定する(effect内でのsetStateによるcascading renderを避ける)。
  // 描画結果(JSX)はisTouchに依存しないため、SSR/クライアントの初期値が
  // 異なってもhydration mismatchは起きない(イベントハンドラの分岐にのみ使う)。
  const [isTouch] = useState(detectNoHover);
  const tooltipId = useId();
  const containerRef = useRef<HTMLSpanElement>(null);

  useEffect(() => {
    if (!open || !isTouch) return;

    function handlePointerDown(event: PointerEvent) {
      if (containerRef.current && !containerRef.current.contains(event.target as Node)) {
        setOpen(false);
      }
    }

    document.addEventListener("pointerdown", handlePointerDown);
    return () => document.removeEventListener("pointerdown", handlePointerDown);
  }, [open, isTouch]);

  function handleKeyDown(event: KeyboardEvent<HTMLSpanElement>) {
    if (event.key === "Escape") {
      setOpen(false);
    }
  }

  return (
    <span
      ref={containerRef}
      className={className ? `info-tooltip ${className}` : "info-tooltip"}
      onKeyDown={handleKeyDown}
    >
      <button
        type="button"
        className="info-tooltip__trigger"
        aria-label={triggerLabel}
        aria-describedby={open ? tooltipId : undefined}
        aria-expanded={open}
        onMouseEnter={() => !isTouch && setOpen(true)}
        onMouseLeave={() => !isTouch && setOpen(false)}
        onFocus={() => !isTouch && setOpen(true)}
        onBlur={() => !isTouch && setOpen(false)}
        onClick={(event) => {
          event.stopPropagation();
          if (isTouch) setOpen((current) => !current);
        }}
      >
        {children ?? <span aria-hidden="true">ⓘ</span>}
      </button>
      <span
        role="tooltip"
        id={tooltipId}
        className={
          open ? "info-tooltip__panel info-tooltip__panel--visible" : "info-tooltip__panel"
        }
      >
        {description}
      </span>
    </span>
  );
}
