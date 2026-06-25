import json
import os
from datetime import datetime, timezone
from urllib.request import Request, urlopen

import boto3


COINGECKO_MARKETS_URL = (
    "https://api.coingecko.com/api/v3/coins/markets"
    "?vs_currency=usd&order=market_cap_desc&per_page=100&page=1&sparkline=false"
    "&price_change_percentage=24h"
)
COINGECKO_TRENDING_URL = "https://api.coingecko.com/api/v3/search/trending"
FEAR_GREED_URL = "https://api.alternative.me/fng/?limit=1"


def _http_get_json(url):
    req = Request(url, headers={"User-Agent": "crypto-pipeline-lambda/1.0"})
    with urlopen(req, timeout=25) as resp:
        return json.loads(resp.read().decode("utf-8"))


def _s3_put_json(s3_client, bucket_name, key, payload):
    s3_client.put_object(
        Bucket=bucket_name,
        Key=key,
        Body=json.dumps(payload, ensure_ascii=True).encode("utf-8"),
        ContentType="application/json",
    )


def lambda_handler(event, context):
    bucket_name = os.getenv("S3_BUCKET_NAME", "")
    if not bucket_name:
        raise ValueError("S3_BUCKET_NAME nao definido")

    now = datetime.now(timezone.utc)
    y = now.strftime("%Y")
    m = now.strftime("%m")
    d = now.strftime("%d")
    bronze_prefix = f"bronze/{y}/{m}/{d}"

    markets = _http_get_json(COINGECKO_MARKETS_URL)
    trending = _http_get_json(COINGECKO_TRENDING_URL)
    fear_greed = _http_get_json(FEAR_GREED_URL)

    s3 = boto3.client("s3")
    _s3_put_json(s3, bucket_name, f"{bronze_prefix}/coingecko_markets.json", markets)
    _s3_put_json(s3, bucket_name, f"{bronze_prefix}/coingecko_trending.json", trending)
    _s3_put_json(s3, bucket_name, f"{bronze_prefix}/fear_greed.json", fear_greed)

    manifest = {
        "extracted_at_utc": now.isoformat(),
        "source": ["coingecko_markets", "coingecko_trending", "fear_greed"],
        "records": {
            "markets": len(markets) if isinstance(markets, list) else None,
            "trending": len((trending or {}).get("coins") or []),
            "fear_greed": len((fear_greed or {}).get("data") or []),
        },
        "bucket": bucket_name,
        "bronze_prefix": bronze_prefix,
    }
    _s3_put_json(s3, bucket_name, f"{bronze_prefix}/manifest.json", manifest)

    return {
        "statusCode": 200,
        "body": json.dumps(
            {
                "status": "ok",
                "bucket": bucket_name,
                "bronze_prefix": bronze_prefix,
                "manifest": manifest,
            },
            ensure_ascii=True,
        ),
    }
