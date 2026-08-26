"""
Phase2 building enrichment エントリポイント

buildings のうち未スコア（llm_scored_at IS NULL）のものだけを対象に、
brand_score（ルールベース分類）とlocation_score（OpenAI API）を生成しDBに保存する。
再実行しても既にスコア済みの建物は再処理しない（コスト・時間の節約）。

2026-08改訂: brand_scoreはLLM推論からルールベース分類に変更した
（app/llm/brand_rules.py 参照）。location_scoreは入力を町名のみに限定し、
Structured Outputsで生成する（app/llm/scorer.py 参照）。

2026-08-26追記: location_scoreはarea_groupとの多重共線性（VIF=12.04）が
判明し、因果推論モデル（matching.py）・適正価格モデル（scoring.py）の
両方から除外した。このスクリプトは引き続きlocation_scoreをDBに保存するが
（監査・記録目的で残置）、モデルには使われていない点に注意。

実行:
  python scripts/run_llm_scoring.py [--limit N] [--force]

  --limit N   処理する建物数の上限（お試し実行用）
  --force     スコア済みの建物も含め全件を再スコアリングする
"""
import argparse
import logging
import os
import sys
from datetime import datetime

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from dotenv import load_dotenv
load_dotenv()

from openai import OpenAI

from app.db.session import SessionLocal
from app.db.models.building import Building
from app.llm.brand_rules import classify_brand_tier
from app.llm.scorer import score_location

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)-7s %(name)s %(message)s",
)
logger = logging.getLogger(__name__)


def main(limit: int | None, force: bool) -> None:
    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        logger.error("OPENAI_API_KEY が設定されていません（.env を確認してください）")
        sys.exit(1)

    client = OpenAI(api_key=api_key)
    db = SessionLocal()

    try:
        query = db.query(Building)
        if not force:
            query = query.filter(Building.llm_scored_at.is_(None))
        if limit:
            query = query.limit(limit)

        buildings = query.all()
        total = len(buildings)
        logger.info("scoring target: %d buildings (force=%s)", total, force)

        scored = 0
        failed = 0
        for i, b in enumerate(buildings, 1):
            tier, matched = classify_brand_tier(b.title)

            loc_result = score_location(b.address, client)
            if loc_result is None:
                failed += 1
                logger.warning("[%d/%d] skip (location score failed): %s", i, total, b.title)
                continue

            b.brand_score = float(tier)
            b.location_score = float(loc_result.location_rank)
            b.llm_reasoning = (
                f"[brand] tier={tier} matched={matched or 'なし'} / "
                f"[location] rank={loc_result.location_rank} {loc_result.reasoning}"
            )[:200]
            b.llm_scored_at = datetime.now()
            db.commit()

            scored += 1
            logger.info(
                "[%d/%d] %s -> brand_tier=%d(%s) location_rank=%d (%s)",
                i, total, b.title, tier, matched or "-", loc_result.location_rank, loc_result.reasoning,
            )

        logger.info("=== done: scored=%d failed=%d / total=%d ===", scored, failed, total)

    finally:
        db.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Phase2 LLM brand/location scoring")
    parser.add_argument("--limit", type=int, default=None, help="処理件数の上限（お試し実行用）")
    parser.add_argument("--force", action="store_true", help="スコア済みの建物も再スコアリングする")
    args = parser.parse_args()
    main(limit=args.limit, force=args.force)
