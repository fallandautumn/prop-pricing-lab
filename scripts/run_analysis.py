"""Phase 1 分析エントリポイント

実行:
  docker compose run --rm api python scripts/run_analysis.py

出力:
  - 因果効果の推定結果（コンソール）
  - estimated_price / divergence_rate を rooms テーブルに保存
  - 割安物件トップ10を表示
"""

import json
import logging
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from dotenv import load_dotenv

load_dotenv()

from app.analysis.matching import (
    estimate_floor_effect,
    estimate_station_distance_effect,
    load_analysis_data,
)
from app.analysis.scoring import (
    build_fair_price_model,
    compute_arbitrage_scores,
    e_value,
    save_scores,
)
from app.db.session import engine

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)-7s %(name)s %(message)s",
)
logger = logging.getLogger(__name__)


def main():
    logger.info("=== Phase 1 分析開始 ===")

    # --- データ読み込み ---
    df = load_analysis_data(engine)
    logger.info(
        "分析対象: %d rooms / %d buildings",
        len(df),
        df["building_id"].nunique(),
    )

    # --- 因果効果推定 ---
    print("\n" + "=" * 60)
    print("【②】階数が家賃に与える因果効果（建物固定効果）")
    print("=" * 60)
    floor_result = estimate_floor_effect(df)
    if "error" in floor_result:
        print(f"  エラー: {floor_result['error']}")
    else:
        print(f"  係数: {floor_result['floor_pct_effect']:+.2f}%/階")
        print(
            f"  95%CI: [{floor_result['ci_95_pct'][0]:+.2f}%, {floor_result['ci_95_pct'][1]:+.2f}%]"
        )
        print(f"  p値:   {floor_result['floor_pval']}")
        print(
            f"  R²:    {floor_result['r2']}  (N={floor_result['n_rooms']}部屋/{floor_result['n_buildings']}棟)"
        )

    print("\n" + "=" * 60)
    print("【①】駅徒歩が家賃に与える因果効果（共変量調整OLS）")
    print("=" * 60)
    station_result = estimate_station_distance_effect(df)
    if "error" in station_result:
        print(f"  エラー: {station_result['error']}")
    else:
        print(f"  係数: {station_result['station_pct_effect']:+.2f}%/分")
        print(
            f"  95%CI: [{station_result['ci_95_pct'][0]:+.2f}%, {station_result['ci_95_pct'][1]:+.2f}%]"
        )
        print(f"  p値:   {station_result['station_pval']}")
        print(
            f"  R²:    {station_result['r2']}  (N={station_result['n_buildings']}棟)"
        )
        print(f"  注意: {station_result['note']}")

        # E-value: 未観測交絡（立地プレミアム）の感度分析（徒歩5分の差におけるリスク比）
        pct_per_min = station_result["station_pct_effect"]
        rr_approx = 1 + (pct_per_min * 5) / 100.0  # 例: -0.32% * 5 = -1.6% -> RR = 0.984
        ev = e_value(rr_approx)
        print(f"\n  [感度分析] E-value = {ev}")
        print(
            f"  → 駅徒歩5分の効果を消すには、未観測交絡が価格に {ev:.2f}倍 の影響を持つ必要がある"
        )

    # --- 適正価格モデル & 裁定スコア ---
    print("\n" + "=" * 60)
    print("【適正価格モデル】DAG informed OLS")
    print("=" * 60)
    try:
        model, df_model, summary = build_fair_price_model(df)
        print(
            f"  R²={summary['r2']}  R²adj={summary['r2_adj']}  N={summary['n']}  (log(price)モデル)"
        )
        print("  主要係数（%効果）:")
        for var, s in summary["coefficients"].items():
            sig = "*" if s["pval"] < 0.05 else " "
            print(
                f"    {sig} {var:20s}: {s['pct_effect']:+.2f}%  "
                f"[{s['ci95_pct'][0]:+.2f}%, {s['ci95_pct'][1]:+.2f}%]  (p={s['pval']})"
            )

        scores = compute_arbitrage_scores(df_model, model)

        # DB に書き戻し
        saved = save_scores(engine, scores)
        print(f"\n  → {saved}件のスコアをDBに保存しました")

        # 割安物件トップ10
        print("\n" + "=" * 60)
        print("【割安物件トップ10】（divergence_rate が最も低い物件）")
        print("=" * 60)
        top10 = (
            scores.sort_values("divergence_rate")
            .head(10)
            .merge(
                df[
                    [
                        "room_id",
                        "building_id",
                        "title",
                        "floor",
                        "floor_plan",
                        "station_distance",
                    ]
                ],
                on="room_id",
            )
        )
        for _, r in top10.iterrows():
            print(
                f"  {r['title'][:20]:<20} "
                f"{r['floor_plan']:<6} {r['floor']:.0f}階  "
                f"駅{r['station_distance']:.0f}分  "
                f"市場:{r['price']:,}円  適正:{r['estimated_price']:,}円  "
                f"乖離:{r['divergence_rate']:+.1%}"
            )

    except ValueError as e:
        print(f"  エラー: {e}")

    logger.info("=== Phase 1 分析完了 ===")


if __name__ == "__main__":
    main()