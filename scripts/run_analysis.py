"""Phase 1/2 分析エントリポイント

実行:
  docker compose run --rm api python scripts/run_analysis.py

出力:
  - 因果効果の推定結果（コンソール）
  - estimated_price / divergence_rate を rooms テーブルに保存
  - 割安物件トップ10を表示
"""

import argparse
import json
import logging
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from dotenv import load_dotenv

load_dotenv()

from app.analysis.cem import bootstrap_cem_att, run_cem
from app.analysis.matching import (
    bootstrap_floor_effect,
    bootstrap_station_effect,
    estimate_floor_effect,
    estimate_station_distance_effect,
    load_analysis_data,
)
from app.analysis.scoring import (
    build_fair_price_model,
    compute_out_of_fold_scores,
    e_value,
    evaluate_fair_price_model_cv,
    save_scores,
)
from app.db.session import engine

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)-7s %(name)s %(message)s",
)
logger = logging.getLogger(__name__)


def main(skip_validation: bool = False):
    logger.info("=== Phase 1/2 分析開始 ===")

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

        if not skip_validation:
            print("  [頑健性チェック] building単位クラスターブートストラップ実行中...")
            boot = bootstrap_floor_effect(df)
            if boot["boot_ci_95_pct"]:
                print(
                    f"  ブートストラップ: 平均={boot['boot_mean_pct']:+.2f}%  "
                    f"SE={boot['boot_se_pct']:.2f}%  "
                    f"95%CI=[{boot['boot_ci_95_pct'][0]:+.2f}%, {boot['boot_ci_95_pct'][1]:+.2f}%]  "
                    f"(成功{boot['n_boot_success']}回)"
                )
                print("  → OLSの正規性の仮定に依存しないCIでも符号・有意性が一致していれば頑健")
            else:
                print("  ブートストラップ失敗（データ不足の可能性）")

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
        print(
            f"  [参考] brand_score:    {station_result['brand_pct_effect']:+.2f}%/pt"
            f"  (p={station_result['brand_pval']})"
        )

        # E-value: 未観測交絡（立地プレミアム）の感度分析（徒歩5分の差におけるリスク比）
        pct_per_min = station_result["station_pct_effect"]
        rr_approx = 1 + (pct_per_min * 5) / 100.0  # 例: -0.32% * 5 = -1.6% -> RR = 0.984
        ev = e_value(rr_approx)
        print(f"\n  [感度分析] E-value = {ev}")
        print(
            f"  → 駅徒歩5分の効果を消すには、未観測交絡が価格に {ev:.2f}倍 の影響を持つ必要がある"
        )

        if not skip_validation:
            print("\n  [頑健性チェック] building単位ブートストラップ実行中...")
            boot = bootstrap_station_effect(df)
            if boot["boot_ci_95_pct"]:
                print(
                    f"  ブートストラップ: 平均={boot['boot_mean_pct']:+.2f}%  "
                    f"SE={boot['boot_se_pct']:.2f}%  "
                    f"95%CI=[{boot['boot_ci_95_pct'][0]:+.2f}%, {boot['boot_ci_95_pct'][1]:+.2f}%]  "
                    f"(成功{boot['n_boot_success']}回)"
                )
            else:
                print("  ブートストラップ失敗（データ不足の可能性）")

    # --- CEM（マッチング法）による①駅徒歩効果の再推定 ---
    print("\n" + "=" * 60)
    print("【①-2】駅徒歩効果の再推定（CEM: Coarsened Exact Matching）")
    print("=" * 60)
    print("  ※連続変数(分)を中央値で「駅近/駅遠」に二値化してマッチング")
    for include_ag in (False, True):
        label = "area_group込み" if include_ag else "area_groupなし"
        print(f"\n  --- {label} ---")
        cem_result = run_cem(df, include_area_group=include_ag)
        if "error" in cem_result:
            print(f"    エラー: {cem_result['error']}")
            continue
        print(f"    中央値分割点: {cem_result['median_split_min']:.1f}分")
        print(f"    ATT: {cem_result['att_pct']:+.2f}%（駅近であることの家賃への効果）")
        print(
            f"    マッチ率: 駅近 {cem_result['treated_coverage']:.1%} "
            f"({cem_result['n_matched_treated']}/{cem_result['n_treated_total']})"
            f" / 駅遠 {cem_result['control_coverage']:.1%} "
            f"({cem_result['n_matched_control']}/{cem_result['n_control_total']})"
        )
        print(
            f"    マッチ成立ストラータム: {cem_result['n_strata_matched']}/{cem_result['n_strata_total']}"
        )
        if cem_result["treated_coverage"] < 0.3:
            print("    → マッチ率が低く、この結果はサンプル不足のため参考程度に留めるべき")

        if not skip_validation:
            boot = bootstrap_cem_att(df, include_area_group=include_ag)
            if boot["boot_ci_95_pct"]:
                print(
                    f"    ブートストラップ95%CI: "
                    f"[{boot['boot_ci_95_pct'][0]:+.2f}%, {boot['boot_ci_95_pct'][1]:+.2f}%]"
                    f"  (成功{boot['n_boot_success']}回)"
                )
            else:
                print("    ブートストラップ失敗（データ不足）")

    # --- 適正価格モデル & 裁定スコア ---
    print("\n" + "=" * 60)
    print("【適正価格モデル】DAG informed OLS")
    print("=" * 60)
    try:
        model, df_model, summary = build_fair_price_model(df)
        print(
            f"  R²={summary['r2']}  R²adj={summary['r2_adj']}  N={summary['n']}  "
            f"(log(price)モデル・全データ学習。係数解釈用。スコアリングはout-of-foldで別途行う)"
        )
        print("  主要係数（%効果）:")
        for var, s in summary["coefficients"].items():
            sig = "*" if s["pval"] < 0.05 else " "
            print(
                f"    {sig} {var:20s}: {s['pct_effect']:+.2f}%  "
                f"[{s['ci95_pct'][0]:+.2f}%, {s['ci95_pct'][1]:+.2f}%]  (p={s['pval']})"
            )

        if not skip_validation:
            print("\n  [検証] building単位 5-fold CV 実行中...")
            cv = evaluate_fair_price_model_cv(df)
            if "error" in cv:
                print(f"  CV失敗: {cv['error']}")
            else:
                std_suffix = f" (±{cv['std_r2']:.3f})" if cv["std_r2"] is not None else ""
                print(
                    f"  out-of-sample R²: 平均={cv['mean_r2']:.3f}{std_suffix}"
                    f"  / in-sample R²={cv['train_r2']:.3f}  ({cv['n_splits']}fold)"
                )
                print(f"  out-of-sample RMSE(log_price): {cv['mean_rmse']:.4f}")
                gap = cv["train_r2"] - cv["mean_r2"]
                print(f"  in-sample - out-of-sample のR²差: {gap:+.3f}", end="  ")
                if gap > 0.1:
                    print("→ 過学習の疑いあり（差が大きい）")
                else:
                    print("→ 過学習は大きくなさそう")
                for fm in cv["fold_metrics"]:
                    print(
                        f"    fold{fm['fold']}: R²={fm['r2']:.3f} RMSE={fm['rmse']:.4f}"
                        f" (test={fm['n_test_used']}件, unseen category除外={fm['n_test_dropped']}件)"
                    )

        # 本番スコアリング: out-of-fold予測（学習データ=推定データ問題を回避）
        print("\n  [本番スコアリング] out-of-fold予測を計算中...")
        scores = compute_out_of_fold_scores(df)
        n_oof = int(scores["is_out_of_fold"].sum())
        n_fallback = len(scores) - n_oof
        print(f"  out-of-fold={n_oof}件 / フォールバック(in-sample)={n_fallback}件")

        # DB に書き戻し
        saved = save_scores(engine, scores)
        print(f"\n  → {saved}件のスコアをDBに保存しました（out-of-fold予測ベース）")

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

    logger.info("=== Phase 1/2 分析完了 ===")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Phase 1/2 分析エントリポイント")
    parser.add_argument(
        "--skip-validation",
        action="store_true",
        help="ブートストラップ・CVをスキップして高速に実行する（お試し実行用）",
    )
    args = parser.parse_args()
    main(skip_validation=args.skip_validation)