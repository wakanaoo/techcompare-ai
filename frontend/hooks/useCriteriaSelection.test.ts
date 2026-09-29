import { act, renderHook } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { useCriteriaSelection } from "./useCriteriaSelection";

describe("useCriteriaSelection", () => {
  it("initializes with the given initial criteria", () => {
    const { result } = renderHook(() => useCriteriaSelection(["development_speed"]));
    expect(result.current.criteria).toEqual(["development_speed"]);
  });

  it("toggleCriterion adds a new value", () => {
    const { result } = renderHook(() => useCriteriaSelection([]));

    act(() => result.current.toggleCriterion("development_speed"));

    expect(result.current.criteria).toEqual(["development_speed"]);
  });

  it("toggleCriterion removes an already-selected value (exact match)", () => {
    const { result } = renderHook(() => useCriteriaSelection(["development_speed"]));

    act(() => result.current.toggleCriterion("development_speed"));

    expect(result.current.criteria).toEqual([]);
  });

  it("toggleCriterion treats a canonical-equivalent value as already selected (case-insensitive match)", () => {
    const { result } = renderHook(() => useCriteriaSelection(["Cost"]));

    act(() => result.current.toggleCriterion("cost"));

    // "Cost"と"cost"は同じcanonical key(大文字小文字を無視した固定候補ラベル)
    // なので、新しく追加するのではなく既存の"Cost"の方を削除する(toggle off)。
    expect(result.current.criteria).toEqual([]);
  });

  it("toggleCriterion does not exceed the maximum of 5 criteria", () => {
    const { result } = renderHook(() =>
      useCriteriaSelection(["a", "b", "c", "d", "e"]),
    );

    act(() => result.current.toggleCriterion("f"));

    expect(result.current.criteria).toEqual(["a", "b", "c", "d", "e"]);
    expect(result.current.reachedMaxCriteria).toBe(true);
  });

  it("addCustomCriterion trims whitespace and adds the value", () => {
    const { result } = renderHook(() => useCriteriaSelection([]));

    act(() => result.current.setCustomInput("  検索の柔軟性  "));
    act(() => result.current.addCustomCriterion());

    expect(result.current.criteria).toEqual(["検索の柔軟性"]);
    expect(result.current.customInput).toBe("");
    expect(result.current.criteriaError).toBeNull();
  });

  it("addCustomCriterion silently ignores an empty/whitespace-only input", () => {
    const { result } = renderHook(() => useCriteriaSelection([]));

    act(() => result.current.setCustomInput("   "));
    act(() => result.current.addCustomCriterion());

    expect(result.current.criteria).toEqual([]);
    expect(result.current.criteriaError).toBeNull();
  });

  it("addCustomCriterion rejects input longer than 40 characters", () => {
    const { result } = renderHook(() => useCriteriaSelection([]));

    act(() => result.current.setCustomInput("a".repeat(41)));
    act(() => result.current.addCustomCriterion());

    expect(result.current.criteria).toEqual([]);
    expect(result.current.criteriaError).toContain("40文字以内");
  });

  it("rejects a custom value that duplicates an existing base/fixed criterion by canonical key", () => {
    const { result } = renderHook(() => useCriteriaSelection(["Development speed"]));

    act(() => result.current.setCustomInput("development speed"));
    act(() => result.current.addCustomCriterion());

    expect(result.current.criteria).toEqual(["Development speed"]);
    expect(result.current.criteriaError).toContain("すでに追加されています");
  });

  it("rejects a custom value that duplicates an AI-suggestion-origin criterion by canonical key", () => {
    // AI提案経由で追加された"Cost"も、custom入力の"cost"と同じcanonical
    // key(大文字小文字を無視した比較)。出自(base/AI/custom)を問わず
    // 同じ判定になることを確認する。
    const { result } = renderHook(() => useCriteriaSelection(["Cost"]));

    act(() => result.current.setCustomInput("cost"));
    act(() => result.current.addCustomCriterion());

    expect(result.current.criteria).toEqual(["Cost"]);
    expect(result.current.criteriaError).toContain("すでに追加されています");
  });

  it("addCustomCriterion rejects input when already at the maximum of 5", () => {
    const { result } = renderHook(() =>
      useCriteriaSelection(["a", "b", "c", "d", "e"]),
    );

    act(() => result.current.setCustomInput("追加項目"));
    act(() => result.current.addCustomCriterion());

    expect(result.current.criteria).toEqual(["a", "b", "c", "d", "e"]);
    expect(result.current.criteriaError).toContain("最大5個まで");
  });
});
