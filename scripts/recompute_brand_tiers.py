"""
brand_score（ルールベースのtier）だけを全件再計算するスクリプト。

app/llm/brand_rules.py のBRAND_TIERSを修正した際、location_scoreの
LLM API呼び出しをやり直さずに済むよう、brand_scoreだけを独立して
再計算できるようにしたもの。APIコストゼロ・即時実行。

実行:
  python scripts/recompute_brand_tiers.py            # dry-run（変更件数のみ表示）
  python scripts/recompute_brand_tiers.py --apply    # 実際にDBを更新する
"""
import argparse
import os
import re
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from dotenv import load_dotenv
load_dotenv()

from app.db.session import SessionLocal
from app.db.models.building import Building
from app.llm.brand_rules import classify_brand_tier

# llm_reasoning内の "[brand] tier=X matched=Y" 部分だけを置き換える
# （"[location] ..." 部分はlocation_scoreのLLM根拠なので触らない）
_BRAND_REASONING_PATTERN = re.compile(r"^\[brand\][^/]*/")


def _updated_reasoning(current: str | None, tier: int, matched: str | None) -> str | None:
    new_brand_part = f"[brand] tier={tier} matched={matched or 'なし'} /"
    if not current:
        return current
    if _BRAND_REASONING_PATTERN.match(current):
        return _BRAND_REASONING_PATTERN.sub(new_brand_part, current, count=1)
    return current  # 想定外のフォーマットは触らない（安全側）


def main(apply: bool) -> None:
    db = SessionLocal()
    try:
        buildings = db.query(Building).all()
        changed = 0
        for b in buildings:
            tier, matched = classify_brand_tier(b.title)
            new_score = float(tier)
            if b.brand_score != new_score:
                changed += 1
            # brand_scoreの値に関わらず、reasoningテキストとの整合性は毎回揃える
            # （値は変わらずtier内訳の表記だけ古いままというケースを防ぐため）
            new_reasoning = _updated_reasoning(b.llm_reasoning, tier, matched)
            if apply:
                b.brand_score = new_score
                if new_reasoning is not None:
                    b.llm_reasoning = new_reasoning

        print(f"対象: {len(buildings)}件 / brand_score変更あり: {changed}件")

        if not apply:
            print("(dry-run。実際に更新するには --apply を付けて再実行してください)")
            return

        db.commit()
        print("更新完了。")

    finally:
        db.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--apply", action="store_true", help="実際にDBを変更する（省略時はdry-run）")
    args = parser.parse_args()
    main(apply=args.apply)
