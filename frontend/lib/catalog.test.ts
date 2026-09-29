import { describe, expect, it } from "vitest";

import {
  findTechnologyIdByName,
  getBaseComparisonCriteria,
  getBasePointDescription,
  getCommonComparisons,
  getRelatedTechnologies,
  getRelation,
  getUseCaseExamples,
} from "./catalog";

describe("getRelation", () => {
  it("finds a relation regardless of argument order (symmetric lookup)", () => {
    const forward = getRelation("fastapi", "django");
    const backward = getRelation("django", "fastapi");

    expect(forward).toBeDefined();
    expect(backward).toBeDefined();
    expect(forward).toBe(backward);
  });

  it("returns undefined when no relation exists between two technologies", () => {
    expect(getRelation("flask", "claude-api")).toBeUndefined();
  });
});

describe("getCommonComparisons", () => {
  it("includes ALTERNATIVE relations", () => {
    const comparisons = getCommonComparisons("fastapi").map((t) => t.id);
    expect(comparisons).toContain("django");
    expect(comparisons).toContain("flask");
  });

  it("includes TRADE_OFF relations", () => {
    const comparisons = getCommonComparisons("postgresql").map((t) => t.id);
    expect(comparisons).toContain("mongodb");
    expect(comparisons).toContain("sqlite");
  });

  it("does not include WORKS_WITH relations", () => {
    const comparisons = getCommonComparisons("fastapi").map((t) => t.id);
    expect(comparisons).not.toContain("postgresql");
    expect(comparisons).not.toContain("mongodb");
    expect(comparisons).not.toContain("gemini-api");
  });

  it("is symmetric: if A lists B, B lists A", () => {
    const fromA = getCommonComparisons("postgresql").map((t) => t.id);
    const fromB = getCommonComparisons("mongodb").map((t) => t.id);
    expect(fromA).toContain("mongodb");
    expect(fromB).toContain("postgresql");
  });
});

describe("getRelatedTechnologies", () => {
  it("includes WORKS_WITH relations", () => {
    const related = getRelatedTechnologies("fastapi").map((t) => t.id);
    expect(related).toContain("postgresql");
    expect(related).toContain("mongodb");
    expect(related).toContain("gemini-api");
  });

  it("does not include ALTERNATIVE/TRADE_OFF relations", () => {
    const related = getRelatedTechnologies("fastapi").map((t) => t.id);
    expect(related).not.toContain("django");
    expect(related).not.toContain("flask");
  });

  it("returns an empty list for a technology with no WORKS_WITH/BUILT_WITH relation", () => {
    expect(getRelatedTechnologies("claude-api")).toEqual([]);
  });
});

describe("getBaseComparisonCriteria", () => {
  it("uses the relation-specific comparisonCriteria when a relation exists", () => {
    const points = getBaseComparisonCriteria("postgresql", "mongodb");
    expect(points).toEqual(["Query capability", "Schema flexibility", "Operations"]);
  });

  it("is order-independent", () => {
    const forward = getBaseComparisonCriteria("postgresql", "mongodb");
    const backward = getBaseComparisonCriteria("mongodb", "postgresql");
    expect(forward).toEqual(backward);
  });

  it("falls back to merged technology-level baseComparisonCriteria when no relation exists", () => {
    const points = getBaseComparisonCriteria("fastapi", "gemini-api");
    expect(points.length).toBeGreaterThan(0);
  });
});

describe("getBasePointDescription", () => {
  it("returns the generic CRITERION_OPTIONS description, case-insensitively", () => {
    expect(getBasePointDescription("learning curve")).toBe(
      "習得のしやすさ。ドキュメントの分かりやすさや、必要な前提知識の少なさ。",
    );
  });

  it("returns the catalog glossary description for a pair-specific Base Point", () => {
    expect(getBasePointDescription("Query capability")).toBe(
      "データの検索・集計をどれだけ柔軟に行えるか。",
    );
  });

  it("returns undefined for an unknown (custom/AI-suggested) point", () => {
    expect(getBasePointDescription("検索の柔軟性")).toBeUndefined();
  });
});

describe("findTechnologyIdByName", () => {
  it("resolves a known technology name case-insensitively", () => {
    expect(findTechnologyIdByName("postgresql")).toBe("postgresql");
    expect(findTechnologyIdByName("PostgreSQL")).toBe("postgresql");
  });

  it("returns undefined for an unknown name", () => {
    expect(findTechnologyIdByName("Rust")).toBeUndefined();
  });
});

describe("getUseCaseExamples", () => {
  it("returns pair-specific curated examples when both ids resolve to a known pair", () => {
    const examples = getUseCaseExamples("postgresql", "mongodb");
    expect(examples).toEqual(getUseCaseExamples("mongodb", "postgresql")); // order-independent
    expect(examples.length).toBeGreaterThan(0);
  });

  it("falls back to generic examples for an unknown or partial pair", () => {
    expect(getUseCaseExamples("rust", "go").length).toBeGreaterThan(0);
    expect(getUseCaseExamples(undefined, undefined).length).toBeGreaterThan(0);
  });
});
