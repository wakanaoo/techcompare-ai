import { describe, expect, it } from "vitest";

import { CATEGORIES } from "./categories";
import { CONCEPTS } from "./concepts";
import { TECHNOLOGIES } from "./technologies";
import { TECHNOLOGY_RELATIONS } from "./relations";

/**
 * Static Technology Catalog / Concept Dictionary / Relationの整合性テスト。
 *
 * これらはPostgreSQLに保存しないstatic curated dataであるため、
 * 「参照先が実在するか」を保証するのはこのテストだけになる
 * (Implementation Plan: static catalog integrity)。
 */
describe("Technology Catalog integrity", () => {
  const categoryIds = new Set(CATEGORIES.map((c) => c.id));
  const conceptIds = new Set(CONCEPTS.map((c) => c.id));
  const technologyIds = new Set(TECHNOLOGIES.map((t) => t.id));

  it("has no duplicate technology ids", () => {
    expect(technologyIds.size).toBe(TECHNOLOGIES.length);
  });

  it("has no duplicate category ids", () => {
    expect(categoryIds.size).toBe(CATEGORIES.length);
  });

  it("has no duplicate concept ids", () => {
    expect(conceptIds.size).toBe(CONCEPTS.length);
  });

  it("every technology references a category that exists", () => {
    for (const tech of TECHNOLOGIES) {
      expect(categoryIds.has(tech.category), `${tech.id} -> ${tech.category}`).toBe(true);
    }
  });

  it("every technology's keyConceptIds reference concepts that exist", () => {
    for (const tech of TECHNOLOGIES) {
      for (const conceptId of tech.keyConceptIds) {
        expect(
          conceptIds.has(conceptId),
          `${tech.id} references missing concept "${conceptId}"`,
        ).toBe(true);
      }
    }
  });

  it("every relation's endpoints (a, b) reference technologies that exist", () => {
    for (const relation of TECHNOLOGY_RELATIONS) {
      expect(
        technologyIds.has(relation.a),
        `relation references missing technology "${relation.a}"`,
      ).toBe(true);
      expect(
        technologyIds.has(relation.b),
        `relation references missing technology "${relation.b}"`,
      ).toBe(true);
    }
  });

  it("no relation connects a technology to itself", () => {
    for (const relation of TECHNOLOGY_RELATIONS) {
      expect(relation.a).not.toBe(relation.b);
    }
  });

  it("has no exact duplicate relation entries (same pair + type)", () => {
    const seen = new Set<string>();
    for (const relation of TECHNOLOGY_RELATIONS) {
      const key = [relation.type, ...[relation.a, relation.b].sort()].join("::");
      expect(seen.has(key), `duplicate relation: ${key}`).toBe(false);
      seen.add(key);
    }
  });

  it("every ALTERNATIVE/TRADE_OFF relation has relationSummary and comparisonCriteria", () => {
    const comparisonRelations = TECHNOLOGY_RELATIONS.filter(
      (r) => r.type === "ALTERNATIVE" || r.type === "TRADE_OFF",
    );
    expect(comparisonRelations.length).toBeGreaterThan(0);
    for (const relation of comparisonRelations) {
      expect(relation.relationSummary, `${relation.a}-${relation.b}`).toBeTruthy();
      expect(relation.comparisonCriteria?.length ?? 0, `${relation.a}-${relation.b}`).toBeGreaterThan(0);
    }
  });

  it("every technology has at least one non-empty baseComparisonCriteria entry", () => {
    for (const tech of TECHNOLOGIES) {
      expect(tech.baseComparisonCriteria.length, tech.id).toBeGreaterThan(0);
    }
  });

  it("prototype scope: only server/data/ai categories have technologies", () => {
    const categoriesInUse = new Set(TECHNOLOGIES.map((t) => t.category));
    expect(categoriesInUse).toEqual(new Set(["server", "data", "ai"]));
  });
});
