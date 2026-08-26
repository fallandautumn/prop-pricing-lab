"""LLMスコアリング結果の分布・失敗件数を確認する。"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from dotenv import load_dotenv
load_dotenv()

from sqlalchemy import text
from app.db.session import engine


def main():
    with engine.connect() as conn:
        total = conn.execute(text("SELECT count(*) FROM buildings")).scalar()
        scored = conn.execute(
            text("SELECT count(*) FROM buildings WHERE llm_scored_at IS NOT NULL")
        ).scalar()
        print(f"総建物数: {total} / スコア済み: {scored} / 未スコア: {total - scored}")

        stats = conn.execute(text("""
            SELECT
                round(avg(brand_score)::numeric, 1)    AS avg_brand,
                round(stddev(brand_score)::numeric, 1) AS std_brand,
                min(brand_score) AS min_brand,
                max(brand_score) AS max_brand,
                round(avg(location_score)::numeric, 1)    AS avg_loc,
                round(stddev(location_score)::numeric, 1) AS std_loc,
                min(location_score) AS min_loc,
                max(location_score) AS max_loc
            FROM buildings WHERE llm_scored_at IS NOT NULL
        """)).one()
        print(f"\nbrand_score(tier 1-5, ルールベース):    avg={stats.avg_brand} std={stats.std_brand} min={stats.min_brand} max={stats.max_brand}")
        print(f"location_score(rank 1-5, LLM):        avg={stats.avg_loc} std={stats.std_loc} min={stats.min_loc} max={stats.max_loc}")

        print("\n--- brand_score(tier) 分布 ---")
        for r in conn.execute(text("""
            SELECT brand_score::int AS tier, count(*) AS n
            FROM buildings WHERE llm_scored_at IS NOT NULL
            GROUP BY tier ORDER BY tier DESC
        """)):
            print(f"  tier={r.tier}: {r.n}件")

        print("\n--- location_score(rank) 分布 ---")
        for r in conn.execute(text("""
            SELECT location_score::int AS rank, count(*) AS n
            FROM buildings WHERE llm_scored_at IS NOT NULL
            GROUP BY rank ORDER BY rank DESC
        """)):
            print(f"  rank={r.rank}: {r.n}件")

        print("\n--- brand_score 上位10 ---")
        for r in conn.execute(text("""
            SELECT title, address, brand_score, location_score, llm_reasoning
            FROM buildings WHERE llm_scored_at IS NOT NULL
            ORDER BY brand_score DESC LIMIT 10
        """)):
            print(f"  {r.brand_score:.0f} / {r.location_score:.0f}  {r.title[:24]:<24}  {r.llm_reasoning}")

        print("\n--- location_score 上位10 ---")
        for r in conn.execute(text("""
            SELECT title, address, brand_score, location_score, llm_reasoning
            FROM buildings WHERE llm_scored_at IS NOT NULL
            ORDER BY location_score DESC LIMIT 10
        """)):
            print(f"  {r.brand_score:.0f} / {r.location_score:.0f}  {r.address[:20]:<20}  {r.llm_reasoning}")

        # station_distanceとの相関（多重共線性チェック）
        corr = conn.execute(text("""
            SELECT corr(location_score, station_distance) AS corr_loc_station,
                   corr(brand_score, age) AS corr_brand_age
            FROM buildings WHERE llm_scored_at IS NOT NULL
        """)).one()
        print(f"\ncorr(location_score, station_distance) = {corr.corr_loc_station:.3f}")
        print(f"corr(brand_score, age)                 = {corr.corr_brand_age:.3f}")
        print("(±0.3以内なら多重共線性の懸念は小さい)")


if __name__ == "__main__":
    main()
