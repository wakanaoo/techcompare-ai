"""Tavily APIを使ったWeb検索(Phase 3)。

コスト・複雑さを抑えるための方針:
- search_depth="basic"を明示し、auto_parameters=Falseにする。
  auto_parametersを有効にすると、Tavilyが意図せずsearch_depthを
  "advanced"(2クレジット消費)へ昇格させることがあるため、
  明示的に"basic"(1クレジット)へ固定している。
- max_results=3で、1クエリあたり上位3件までに制限する
  (item_a用・item_b用でそれぞれ最大3件、計最大6件の情報源)。
- include_raw_content="text"で、ページの実際の本文(プレーンテキスト)を
  取得する。これはLLMに自由に引用文を生成させず、Evidence Viewerで
  表示する根拠本文を「実際にWeb上にあったテキスト」にするため。
"""

from dataclasses import dataclass

from tavily import TavilyClient

MAX_RESULTS_PER_QUERY = 3

# DBに保存する本文の長さの上限(ページ全体を無制限に保存しないため)。
_CONTENT_MAX_LENGTH = 3000


@dataclass
class SearchResultItem:
    title: str
    url: str
    content: str


def search_technology(item_name: str) -> list[SearchResultItem]:
    """指定した技術名についてTavilyで検索し、上位数件の情報源を返す。

    TAVILY_API_KEY環境変数からキーを自動取得する(TavilyClient()のデフォルト挙動)。
    """
    client = TavilyClient()

    response = client.search(
        query=f"{item_name} 公式ドキュメント",
        search_depth="basic",
        auto_parameters=False,
        max_results=MAX_RESULTS_PER_QUERY,
        include_raw_content="text",
    )

    items: list[SearchResultItem] = []
    for result in response.get("results", []):
        content = (result.get("raw_content") or result.get("content") or "").strip()
        if not content:
            continue
        items.append(
            SearchResultItem(
                title=result.get("title") or result.get("url", ""),
                url=result.get("url", ""),
                content=content[:_CONTENT_MAX_LENGTH],
            )
        )
    return items
