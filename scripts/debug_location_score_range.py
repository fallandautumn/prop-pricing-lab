"""
location_scoreの分散を意図的に両極端な住所でテストする診断スクリプト。

n=5のランダムサンプルがたまたま「際立って高級でも下町でもない」エリアに
偏っていた可能性があるため、既知の高級エリアと既知の庶民的エリアを
意図的に混ぜてテストし、LLMが本当にレンジを使い切れるか確認する。

実行:
  python scripts/debug_location_score_range.py
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from dotenv import load_dotenv
load_dotenv()

from openai import OpenAI

from app.llm.scorer import score_location

# (住所, 事前の期待感 = 高級/標準/庶民的 のメモ。あくまで参考、正解ラベルではない)
TEST_ADDRESSES = [
    ("東京都渋谷区松濤1", "高級住宅街の代表格"),
    ("東京都渋谷区南平台町", "高級住宅街"),
    ("東京都渋谷区広尾1", "高級・大使館エリア"),
    ("東京都渋谷区神宮前5", "トレンドエリア"),
    ("東京都渋谷区鉢山町", "代官山近接の住宅街"),
    ("東京都渋谷区笹塚1", "標準的な住宅地"),
    ("東京都新宿区高田馬場1", "学生街"),
    ("東京都新宿区西新宿7", "オフィス街寄り"),
    ("東京都新宿区大久保1", "繁華街近接"),
]


def main():
    client = OpenAI(api_key=os.environ["OPENAI_API_KEY"])
    results = []
    for address, note in TEST_ADDRESSES:
        r = score_location(address, client)
        if r is None:
            print(f"{address:20s} ({note}): 失敗")
            continue
        results.append(r.location_rank)
        print(f"{address:20s} ({note}): rank={r.location_rank}  {r.reasoning}")

    if results:
        print(f"\nrange: {min(results)} 〜 {max(results)}  (幅={max(results)-min(results)})")


if __name__ == "__main__":
    main()
