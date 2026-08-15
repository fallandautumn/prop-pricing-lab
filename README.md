# prop-arbitrage-v2

渋谷区の賃貸物件データ（Suumo）に対して因果推論を適用し、「適正価格」と市場価格の乖離（裁定スコア）を算出するエンジン。

```
Suumo Scraper → PostgreSQL → 因果推論モデル → 適正価格・裁定スコア → FastAPI
```

v1（単純な重回帰、R²=0.86）からの発展として、「駅徒歩」「階数」が家賃に与える純粋な因果効果を交絡因子を制御した上で推定し、そこから算出した適正価格との残差を裁定スコアとして使う設計にしている。

詳細な設計判断・推定結果・見つけたバグの記録は [`docs/phase1_summary.md`](docs/phase1_summary.md) を参照。

## 技術スタック

- Python 3.12 / FastAPI / SQLAlchemy 2.0 / Alembic
- PostgreSQL 15 / Docker Compose
- pandas / statsmodels（因果推論・回帰分析）
- requests / BeautifulSoup4（スクレイピング）

## セットアップ

```bash
cp .env.example .env
docker compose up -d db
docker compose run --rm api alembic upgrade head
```

## 使い方

```bash
# スクレイピング（渋谷区、1〜30ページ）
docker compose run --rm --build api python scripts/run_scraper.py --max-pages 30

# 因果推論モデルの実行・裁定スコアのDB書き戻し
docker compose run --rm api python scripts/run_analysis.py

# APIサーバー起動
docker compose up api
# -> http://localhost:8000/docs
```

`GET /rooms` で `divergence_rate`（裁定スコア）順に物件を取得できる。`sort` / `order` / `max_divergence_rate` / `building_type` / `floor_plan` 等でフィルタ可能。

## ディレクトリ構成

```
app/
  scraper/     # Suumoスクレイパー（listing → building → room の3段階）
  db/          # SQLAlchemyモデル・セッション
  analysis/    # DAG定義・因果効果推定・適正価格モデル
  api/         # FastAPIルーター・スキーマ
scripts/       # 実行エントリポイント（scraper / analysis / debug用）
alembic/       # DBマイグレーション
docs/          # Phase毎のまとめ
```

## 対象エリア・スコープ

現時点では渋谷区・集合住宅（マンション・アパート）に限定。一戸建ては別テンプレートで価格が取得できないためスコープ外（詳細は `docs/phase1_summary.md`）。地域・建物タイプの拡張はPhase 2以降で対応予定。
