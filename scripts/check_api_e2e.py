"""
FastAPIエンドポイントのエンドツーエンド動作確認。

/health, /rooms（デフォルトソート＝割安順）, /rooms/{id}, フィルタ付き検索
の4パターンを実際に叩いて、レスポンスが正しい形・妥当な値で返ってくるかを確認する。

実行:
  python scripts/check_api_e2e.py
"""
import sys

import requests

BASE = "http://localhost:8000"


def check(name: str, resp: requests.Response) -> dict | None:
    ok = resp.status_code == 200
    print(f"[{'OK' if ok else 'NG'}] {name}: status={resp.status_code}")
    if not ok:
        print(f"      body={resp.text[:300]}")
        return None
    return resp.json()


def main() -> None:
    # 1. health check
    data = check("GET /health", requests.get(f"{BASE}/health"))
    if data is None or data.get("status") != "ok":
        print("health check失敗。APIが起動しているか確認してください。")
        sys.exit(1)

    # 2. デフォルトソート（divergence_rate昇順=割安順）
    data = check("GET /rooms?limit=5", requests.get(f"{BASE}/rooms", params={"limit": 5}))
    if data is None:
        sys.exit(1)
    print(f"      total={data['total']}  items={len(data['items'])}")
    rates = [item["divergence_rate"] for item in data["items"]]
    is_sorted = all(rates[i] <= rates[i + 1] for i in range(len(rates) - 1))
    print(f"      divergence_rate昇順になっているか: {is_sorted}  values={rates}")
    for item in data["items"][:3]:
        print(
            f"      - {item['title']} {item['floor_plan']} "
            f"市場:{item['price']}円 適正:{item['estimated_price']}円 "
            f"乖離:{item['divergence_rate']*100:.1f}%"
        )

    # 3. 個別room取得（上のリストの先頭を使う）
    first_id = data["items"][0]["room_id"]
    detail = check(f"GET /rooms/{first_id}", requests.get(f"{BASE}/rooms/{first_id}"))
    if detail is None:
        sys.exit(1)
    print(f"      room_id={detail['room_id']} title={detail['title']}")

    # 4. フィルタ付き（10%以上割安のみ・価格帯指定）
    data = check(
        "GET /rooms?max_divergence_rate=-0.1&min_price=100000&max_price=300000",
        requests.get(
            f"{BASE}/rooms",
            params={"max_divergence_rate": -0.1, "min_price": 100000, "max_price": 300000, "limit": 5},
        ),
    )
    if data is None:
        sys.exit(1)
    print(f"      total={data['total']}件（10%以上割安 かつ 10万〜30万円）")
    for item in data["items"][:3]:
        print(f"      - {item['title']} 市場:{item['price']}円 乖離:{item['divergence_rate']*100:.1f}%")

    # 5. 存在しないroom_id（404確認）
    resp = requests.get(f"{BASE}/rooms/99999999")
    print(f"[{'OK' if resp.status_code == 404 else 'NG'}] GET /rooms/99999999（存在しないID）: status={resp.status_code}")

    print("\n=== 全チェック完了 ===")


if __name__ == "__main__":
    main()
