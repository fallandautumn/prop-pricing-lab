"""
ブランドtierの分布と、tier4・tier5に分類された建物の全件一覧を出力する。

ログをスクロールして偶然おかしいものを見つけるのではなく、まとめて
目視レビューして BRAND_TIERS の誤りを網羅的に洗い出すためのスクリプト。
（brand_scoreが既に計算済みの建物が対象。まだの建物はtitleから
その場でclassify_brand_tierを計算して仮表示する）

実行:
  python scripts/review_brand_tiers.py
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from dotenv import load_dotenv
load_dotenv()

from app.db.session import SessionLocal
from app.db.models.building import Building
from app.llm.brand_rules import classify_brand_tier


def main():
    db = SessionLocal()
    try:
        buildings = db.query(Building).all()

        results = []
        for b in buildings:
            tier, matched = classify_brand_tier(b.title)
            results.append((tier, matched, b.title))

        print(f"対象: {len(results)}件\n")

        print("--- tier分布 ---")
        for t in (5, 4, 3, 2, 1):
            n = sum(1 for r in results if r[0] == t)
            print(f"  tier={t}: {n}件")

        for target_tier in (5, 4):
            print(f"\n--- tier={target_tier} 全件一覧 ---")
            matches = sorted(
                [(matched, title) for tier, matched, title in results if tier == target_tier]
            )
            for matched, title in matches:
                print(f"  {matched:12s} <- {title}")
            print(f"  ({len(matches)}件)")

    finally:
        db.close()


if __name__ == "__main__":
    main()
