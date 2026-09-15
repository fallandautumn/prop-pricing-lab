"""
deposit（敷金）・key_money（礼金）の取得率を確認する。

背景: Suumoのroom詳細ページでは「敷金」「礼金」という単独のth文字列が
存在せず、shoplist（取扱店舗一覧）テーブルの「敷/礼/保証/敷引・償却」
という結合thにスラッシュ区切りでまとめられている。room.pyの現在の
抽出ロジック（"敷金" in key / "礼金" in key）はこの結合thにマッチしない
ため、常にNoneになっている可能性がある。

実行:
  python scripts/check_deposit_key_money_rate.py
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from dotenv import load_dotenv
load_dotenv()

from sqlalchemy import text

from app.db.session import engine

if __name__ == "__main__":
    query = text("""
        SELECT
            COUNT(*) AS total,
            COUNT(deposit) AS with_deposit,
            COUNT(key_money) AS with_key_money,
            COUNT(*) FILTER (WHERE deposit IS NOT NULL AND key_money IS NOT NULL) AS with_both,
            COUNT(*) FILTER (WHERE price IS NOT NULL) AS with_price
        FROM rooms
    """)
    with engine.connect() as conn:
        row = conn.execute(query).fetchone()

    def rate(n, total):
        return n / total * 100 if total else 0

    print(f"全room数: {row.total}（price取得済み: {row.with_price}）")
    print(f"deposit取得済み: {row.with_deposit} ({rate(row.with_deposit, row.total):.1f}%)")
    print(f"key_money取得済み: {row.with_key_money} ({rate(row.with_key_money, row.total):.1f}%)")
    print(f"両方取得済み: {row.with_both} ({rate(row.with_both, row.total):.1f}%)")

    # サンプル: NULLになっている行を数件表示（値自体が本当に"-"（無し）なのか、
    # 抽出ロジックの不備で取れていないだけなのかは、rooms.urlを直接開いて要確認）
    sample_query = text("""
        SELECT id, suumo_room_id, price, deposit, key_money, url
        FROM rooms
        WHERE deposit IS NULL OR key_money IS NULL
        LIMIT 5
    """)
    with engine.connect() as conn:
        samples = conn.execute(sample_query).fetchall()

    print("\ndeposit/key_moneyがNULLな行のサンプル（url先を直接確認して「本当に無し」か「取得漏れ」か判定）:")
    for s in samples:
        print(f"  id={s.id} room_id={s.suumo_room_id} price={s.price} deposit={s.deposit} key_money={s.key_money}")
        print(f"    {s.url}")
