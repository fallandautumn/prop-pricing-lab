# prop-arbitrage-v2

渋谷区の賃貸物件データ（Suumo）に因果推論とLLM特徴量を組み合わせ、「適正価格」と市場価格の乖離（裁定スコア）から割安物件を発見するエンジン。

```
Suumo Scraper（listing→building→room 3段階）
      ↓
PostgreSQL（buildings / rooms）
      ↓
特徴量エンジニアリング（ルールベースLLM: 建物ブランドtier分類）
      ↓
因果推論（DAGに基づく交絡因子制御 / CEM / 感度分析）
      ↓
適正価格モデル（log-logヘドニックモデル、out-of-fold予測）
      ↓
裁定スコア = (市場価格 - 適正価格) / 適正価格
      ↓
FastAPI（/rooms で乖離率順に取得）
```

v1（単純な重回帰、R²=0.86）からの反省を踏まえ、①全部屋スクレイピング（v1は建物につき1部屋のみだった）、②分析ロジックとDBアクセスの分離、③交絡因子を制御した因果推論、の3点を軸に作り直した。

## 主要な結果

Phase2完了時点（[`docs/phase2_summary.md`](docs/phase2_summary.md) 2節と同じ最終値）。

| 項目 | 結果 |
|---|---|
| 階数が家賃に与える因果効果（建物固定効果, N=1,715部屋/326棟） | **+0.85%/階**（p<0.001、ブートストラップCI [+0.65%, +1.14%]で頑健性確認済み） |
| 駅徒歩が家賃に与える因果効果（3手法で検証） | 共変量調整OLS: -0.28%/分（p=0.119, 非有意）／ CEM（area_group込み）: +2.33%（非有意）／ いずれも95%CIが0を跨ぐ→検出力不足と判断 |
| 適正価格モデル（log-priceヘドニックモデル） | R²=0.926（in-sample）/ 0.914（building単位5-fold out-of-sample）、N=2,698部屋 |
| 適正価格モデル station_distance / brand_score | -0.41%（p=0.0006）／ +1.74%（p<0.001, ルールベースtier 1段階あたり） |
| 裁定スコア（out-of-fold予測ベース） | 割安1,033件・割高970件（乖離率±5%基準） |

対象データ: 渋谷区の集合住宅1,925建物・全部屋スクレイピング（価格ありroom 2,998件）。

## このプロジェクトで実際にやったこと

- **DAGに基づく交絡因子の制御**: 「駅徒歩」「階数」の家賃への因果効果を、単純回帰ではなく交絡因子（築年数・総階数・立地）を明示的に制御した上で推定。station_distanceは町名固定効果（area_group）を入れないと符号が逆転することを実データで確認。
- **単一手法に依存しない頑健性の確認**: 駅徒歩効果を共変量調整OLS・クラスターブートストラップ・CEM（Coarsened Exact Matching）の3つの独立した手法で検証し、一貫して同じ結論（非有意）に到達。E-value感度分析で未観測交絡の影響も定量化。
- **本番スコアリングのリーク対策**: 全データで学習したモデルで同じデータを採点すると、固定効果を通じて自分自身の価格が「適正価格」に混ざり込むリークが生じる。building単位K-foldのout-of-fold予測（Double MLのcross-fittingと同じ発想）でこれを解消。
- **LLM特徴量を検証してから採用/棄却**: 建物ブランドをLLM推論からルールベース分類に変更（決定論的・APIコストゼロ）。もう一つのLLM特徴量（立地スコア）はarea_groupとの多重共線性をVIF・クラスターロバストSE・モデル比較（AIC/BIC/out-of-sample性能）の3方向から検証し、実質的な寄与がないと判明したため最終的にモデルから除外。
- **データ品質のバグを実データから発見・修正**: スクレイパーの建物名抽出バグ（3パターン）、同一物理部屋の重複掲載（複数不動産会社経由）を、割安トップ10の異常値から逆算して発見し、名寄せロジックを設計・修正。

詳細な設計判断・失敗と修正の記録は [`docs/phase1_summary.md`](docs/phase1_summary.md)（因果推論の基礎部分）と [`docs/phase2_summary.md`](docs/phase2_summary.md)（LLM特徴量・検証フレームワーク・データ品質バグ修正、目次あり）を参照。

## 技術スタック

- Python 3.12 / FastAPI / SQLAlchemy 2.0 / Alembic
- PostgreSQL 15 / Docker Compose
- pandas / statsmodels（因果推論・回帰分析）
- OpenAI API（gpt-4o-mini, Structured Outputs）
- requests / BeautifulSoup4（スクレイピング）

## セットアップ

```bash
cp .env.example .env
docker compose up -d db
docker compose run --rm api alembic upgrade head
```

## 使い方

```bash
# スクレイピング（渋谷区、全ページ）
docker compose run --rm --build api python scripts/run_scraper.py

# LLMブランドスコアリング（ルールベース、無料）
docker compose run --rm api python scripts/run_llm_scoring.py

# 因果推論モデルの実行・裁定スコアのDB書き戻し
docker compose run --rm api python scripts/run_analysis.py

# APIサーバー起動
docker compose up api
# -> http://localhost:8000/docs
```

`GET /rooms` で `divergence_rate`（裁定スコア）順に物件を取得できる。`sort` / `order` / `max_divergence_rate` / `building_type` / `floor_plan` / `min_price` / `max_price` 等でフィルタ可能。`GET /rooms/{id}` で単一物件の詳細を取得できる。

## ディレクトリ構成

```
app/
  scraper/     # Suumoスクレイパー（listing → building → room の3段階）
  db/          # SQLAlchemyモデル・セッション
  llm/         # ブランドtierルールベース分類・LLM立地スコアリング（Structured Outputs）
  analysis/    # DAG定義・因果効果推定（matching.py）・CEM（cem.py）・適正価格モデル（scoring.py）
  api/         # FastAPIルーター・スキーマ
scripts/       # 実行エントリポイント（scraper / analysis / LLM採点 / データ品質診断・修正用）
alembic/       # DBマイグレーション
docs/          # Phase毎のまとめ（設計判断・推定結果・見つけたバグの記録）
```

## 対象エリア・スコープ

渋谷区・集合住宅（マンション・アパート）に限定。一戸建ては別テンプレートで価格が取得できないためスコープ外。新宿区への拡張も一時検討したが、町名ベースの固定効果（area_group）は隣区のデータで補強されないため根本解決にならないと判明し、渋谷区の密度向上に方針転換した（詳細は`docs/phase2_summary.md` 7.1節）。

## 既知の限界・今後の方向性

- 駅徒歩効果は3手法とも非有意。真にゼロなのか検出力不足なのかはこのデータでは切り分けられない（エリア拡張でサンプルを増やせば検証できる可能性がある）。
- 建物構造（RC/SRC/木造等）は全件（1,925建物・100%）取得できているが、現状の因果推論・適正価格モデルにはまだ変数として組み込んでいない。構造による価格差は交絡因子として重要な可能性があり、追加の余地がある。
- 契約形態（普通借家/定期借家）は未取得。同一物件でも取扱店舗によって契約形態・管理費が異なるケースがあり、系統的な交絡因子になる可能性がある。
- 予測性能はLightGBM等の非線形モデルで向上の余地がある。
- 地価データ・PostGIS統合は今回のスコープでは見送った。PostgreSQL 15を採用しているのはこの拡張を見据えたためで、町名固定効果（area_group）より連続的な地理情報を使えば、より精緻な立地プレミアムの制御ができる可能性がある。
