"use client";

import { useEffect, useState } from "react";

/**
 * 実際の開始時刻(backendの`created_at`等、本物のタイムスタンプ)からの
 * 経過秒数を1秒ごとに更新して返す。
 *
 * 画面mount時刻ではなく、呼び出し側が渡した本当の開始時刻を基準にする
 * (「調査開始からの経過時間」を誤認させないため)。
 *
 * active が false になったら(completed/failed等)、それ以上は加算せず
 * 最後に計算した値のまま止める。
 */
export function useElapsedSeconds(
  startedAt: string | null | undefined,
  active: boolean,
): number {
  const [elapsedSeconds, setElapsedSeconds] = useState(0);

  useEffect(() => {
    if (!startedAt) {
      // 呼び出し側(Progress画面)は、経過時間を表示する条件(isActive等)を
      // researchがnullでない場合に限っているため、ここでは値を更新せず
      // 何もしない(次にstartedAtが有効になった時点でtick()が更新する)。
      return;
    }

    const startMs = new Date(startedAt).getTime();

    function tick() {
      setElapsedSeconds(Math.max(0, Math.floor((Date.now() - startMs) / 1000)));
    }

    tick();

    if (!active) {
      return;
    }

    const intervalId = setInterval(tick, 1000);
    return () => clearInterval(intervalId);
  }, [startedAt, active]);

  return elapsedSeconds;
}
