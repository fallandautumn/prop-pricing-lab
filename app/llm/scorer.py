"""
Phase2改訂: location_rankのみをOpenAI API (gpt-4o-mini) で生成する。

変更履歴（2026-08、ユーザーからの設計指摘を反映）:
- brand_scoreはルールベース化したため、このモジュールでは扱わない
  （app/llm/brand_rules.py の classify_brand_tier を使う）。
- 入力を町名（address）のみに限定し、建物名・価格を渡さない。
  以前はbrand_score/location_scoreを同一コンテキスト・同一プロンプトで
  同時生成しており、「良い建物名だから良いエリアのはず」というハロー効果で
  スコア同士が人工的に相関するリスクがあった。入力を分離することで
  根本的に排除する。
- response_format を Structured Outputs (json_schema, strict=True) に変更。
  旧実装の {"type": "json_object"} はJSON構文こそ保証するが、キー名・型
  までは保証しないためパース失敗の余地があった。strict modeでスキーマ
  自体を保証する。さらに location_rank には enum: [1,2,3,4,5] を指定し、
  範囲外の値が生成される余地自体を構造的になくした。
- 0-100の連続値から1-5の5段階ランクに変更した。連続値は見かけ上の精度
  でしかなく（結局は内部で5段階の基準に当てはめて数値化していただけ）、
  brand_scoreと同じ順序尺度に揃えることで扱いを一貫させる。副次効果として、
  APIのtemperature=0でも生じる若干の非決定性（同一入力で近い値がブレる
  現象を確認済み）が、離散ランクに丸められることで実務上目立たなくなる。
- temperature=0 で再現性を優先する（既存方針を維持）。
"""
import json
import logging
import time
from dataclasses import dataclass

from openai import OpenAI, APIError, RateLimitError

logger = logging.getLogger(__name__)

MODEL = "gpt-4o-mini"

SYSTEM_PROMPT = """\
あなたは日本の不動産市場に詳しいアナリストです。
以下の町名（住所の一部）から、その地域の「立地ランク」を1〜5の5段階で評価してください。

評価対象は町名のみです。建物名や家賃は意図的に与えられていません。
駅からの距離は既に別の変数として分析済みなので、評価に含めないでください。

### location_rank（町名から判定 ※東京23区基準）
  1: 郊外型・利便性や知名度が低い密集住宅地
  2: 一般的な住宅地（特筆すべきブランド力はない）
  3: 利便性の高い人気居住エリア
  4: 商業集積地または知名度の高い有名エリア
  5: 都内屈指の超高級住宅街・一等地（例: 松濤、南平台町、代官山町、広尾、南青山等）

対象は現在渋谷区・新宿区だが、他区の知識も踏まえて絶対的な評価基準で
判断すること。「情報が乏しいから中間値」という判断はせず、地名から
読み取れる特徴を根拠に評価すること。reasoningを先に書き、その根拠に
基づいてrankを決めること（rankだけを先に決めて後付けで理由を書かないこと）。
"""

RESPONSE_SCHEMA = {
    "type": "json_schema",
    "json_schema": {
        "name": "location_rank_result",
        "strict": True,
        "schema": {
            "type": "object",
            "properties": {
                "reasoning": {
                    "type": "string",
                    "description": "120字以内。何を手がかりにどのランクと判断したか。",
                },
                "location_rank": {"type": "integer", "enum": [1, 2, 3, 4, 5]},
            },
            "required": ["reasoning", "location_rank"],
            "additionalProperties": False,
        },
    },
}

MAX_RETRIES = 3
RETRY_BACKOFF_SEC = 2.0


@dataclass
class LocationScoreResult:
    location_rank: int
    reasoning: str


def score_location(address: str, client: OpenAI) -> LocationScoreResult | None:
    """
    町名（address）だけから location_rank(1-5) を生成する。
    建物名・価格などbrand_score算出に使う情報は意図的に渡さない
    （ハロー効果によるスコア間の人工的な相関を防ぐため）。
    失敗時（API エラー・パース失敗）は None を返す（呼び出し側でスキップ扱いにする）。
    """
    user_prompt = f"町名: {address or '(不明)'}"

    for attempt in range(1, MAX_RETRIES + 1):
        try:
            resp = client.chat.completions.create(
                model=MODEL,
                temperature=0,
                response_format=RESPONSE_SCHEMA,
                messages=[
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": user_prompt},
                ],
            )
            raw = resp.choices[0].message.content
            data = json.loads(raw)

            rank = int(data["location_rank"])
            reasoning = str(data.get("reasoning", ""))[:200]
            rank = max(1, min(5, rank))  # 念のためのクリップ（enum制約で通常不要）

            return LocationScoreResult(location_rank=rank, reasoning=reasoning)

        except (RateLimitError, APIError) as e:
            logger.warning("OpenAI API error (attempt %d/%d): %s", attempt, MAX_RETRIES, e)
            time.sleep(RETRY_BACKOFF_SEC * attempt)
        except (json.JSONDecodeError, KeyError, ValueError, TypeError) as e:
            logger.error("LLM response parse failed for %r: %s", address, e)
            return None
        except Exception as e:
            logger.error("unexpected error scoring %r: %s", address, e)
            return None

    logger.error("gave up scoring %r after %d retries", address, MAX_RETRIES)
    return None
