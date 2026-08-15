"""
DAG: 渋谷区賃貸物件の価格決定因果構造

=== 変数 ===
Y  : price          賃料（目的変数）
T1 : station_distance  駅徒歩分（治療変数①）
T2 : floor          部屋の階数（治療変数②）
W1 : age            築年数（交絡因子）
W2 : liv_area       専有面積（交絡因子）
W3 : total_floors   建物総階数（交絡因子）
W4 : floor_plan     間取り（交絡因子）
U  : location       立地プレミアム（未観測交絡）

=== 因果辺とその根拠 ===
age → price
    新しいほど設備・断熱が良く家賃が高い

age → station_distance  ← 交絡！
    駅近エリアは再開発が進み築浅物件が多い
    → 単純回帰では「駅近効果」に「築浅効果」が混入する

station_distance → price  [推定したい①]
    駅が遠いほど家賃が下がる（利便性の直接効果）

floor → price  [推定したい②]
    上階ほど眺望・防犯・騒音が改善し家賃が高い

total_floors → floor
    高層ビルにしか高い階は存在しない（選択バイアス）

total_floors → price
    高層ビルはブランド・管理体制で価格プレミアム

liv_area → price
    面積が大きいほど家賃が高い

floor_plan → price
    1LDK > 1DK > 1K など間取りで価格帯が変わる

location(U) → station_distance
    都心立地は駅密度が高く徒歩分が短い傾向

location(U) → price
    同じ駅距離でも渋谷寄りは高い（未観測）

=== バックドアパスと識別戦略 ===

①駅徒歩効果の識別:
  バックドア: station_distance ← age → price
              station_distance ← location → price
  調整集合: {age, total_floors, floor_plan, liv_area}
  推定法: 調整OLS（共変量を制御した線形回帰）
  限界: location(U) は未観測 → 感度分析（E-value）で影響を定量化する

②階数効果の識別:
  バックドア: floor ← total_floors → price
  建物固定効果（C(building_id)）で全建物レベル変数を一括制御
  → 同一建物内の部屋間比較のみで効果を推定（最もクリーン）
  残る交絡: liv_area・floor_plan（上階が広い可能性）→ これも制御する
  有効条件: 同一building_idに3部屋以上あること

=== 適正価格モデルへの接続 ===
因果効果の推定結果（各変数の係数）を使って適正価格を算出する。
  estimated_price = β0 + β1*station_distance + β2*floor
                       + β3*liv_area + β4*age + β5*total_floors
                       + Σ γk*floor_plan_k

残差 = price - estimated_price
  残差 < 0 → 市場価格が適正より安い → 割安物件（裁定機会）
  残差 > 0 → 市場価格が適正より高い → 割高物件
"""

# networkx を使った DAG オブジェクト（可視化・パス列挙に使える）
# 現状は文書化目的のみ。Phase 2 で dowhy と連携予定。

def build_dag() -> dict:
    """
    DAG をエッジリストとして返す。
    各エッジは (from, to, type) のタプル。
    type: 'causal' = 推定したい効果, 'confound' = 交絡, 'covariate' = 共変量
    """
    edges = [
        # 推定したい因果効果
        ("station_distance", "price",   "causal"),
        ("floor",            "price",   "causal"),
        # 交絡因子
        ("age",              "price",   "covariate"),
        ("age",              "station_distance", "confound"),
        ("total_floors",     "price",   "covariate"),
        ("total_floors",     "floor",   "confound"),
        ("liv_area",         "price",   "covariate"),
        ("floor_plan",       "price",   "covariate"),
        # 未観測交絡（参考）
        ("location_U",       "station_distance", "unobserved"),
        ("location_U",       "price",   "unobserved"),
    ]
    return {
        "nodes": ["price", "station_distance", "floor", "age",
                  "total_floors", "liv_area", "floor_plan", "location_U"],
        "edges": edges,
        # バックドア調整集合
        "adjustment_sets": {
            "station_distance": ["age", "total_floors", "liv_area", "floor_plan"],
            "floor":            ["liv_area", "floor_plan"],  # + building FE
        },
    }

