import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

THRESHOLD_ESTAVEL = 2.0
HIGH_LIQUIDITY_VOLUME = 1_000_000_000


def _data_root() -> Path:
    preferred = Path("/opt/airflow/data")
    return preferred if preferred.exists() else Path("data")


def _safe_float(value: Any) -> Optional[float]:
    try:
        if value is None:
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def _classificar_variacao(variacao: Optional[float]) -> str:
    if variacao is None:
        return "desconhecido"
    if variacao > THRESHOLD_ESTAVEL:
        return "alta"
    if variacao < -THRESHOLD_ESTAVEL:
        return "queda"
    return "estavel"


def _parse_timestamp(last_updated: Optional[str], run_date: str) -> str:
    if last_updated:
        try:
            return datetime.fromisoformat(last_updated.replace("Z", "+00:00")).isoformat()
        except ValueError:
            pass
    return f"{run_date}T00:00:00+00:00"


def _load_json(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def _write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=True, indent=2)


def _bronze_dir(run_date: str) -> Path:
    dt = datetime.strptime(run_date, "%Y-%m-%d")
    return _data_root() / "bronze" / dt.strftime("%Y") / dt.strftime("%m") / dt.strftime("%d")


def _silver_dir(run_date: str) -> Path:
    dt = datetime.strptime(run_date, "%Y-%m-%d")
    return _data_root() / "silver" / dt.strftime("%Y") / dt.strftime("%m") / dt.strftime("%d")


def _normalizar_markets(markets_payload: List[Dict[str, Any]], run_date: str) -> Tuple[List[Dict[str, Any]], Dict[str, int]]:
    quality = {
        "registros_entrada": len(markets_payload),
        "registros_validos": 0,
        "campos_nulos": 0,
        "deduplicados": 0,
    }

    dedup: Dict[Tuple[str, str], Dict[str, Any]] = {}

    for item in markets_payload:
        coin_id = item.get("id")
        if not coin_id:
            quality["campos_nulos"] += 1
            continue

        timestamp = _parse_timestamp(item.get("last_updated"), run_date)
        variacao_pct_24h = _safe_float(item.get("price_change_percentage_24h"))
        total_volume = _safe_float(item.get("total_volume"))
        current_price = _safe_float(item.get("current_price"))
        market_cap = _safe_float(item.get("market_cap"))

        if current_price is None or market_cap is None:
            quality["campos_nulos"] += 1
            continue

        normalized = {
            "coin_id": coin_id,
            "symbol": (item.get("symbol") or "").upper(),
            "name": item.get("name"),
            "currency": "USD",
            "timestamp": timestamp,
            "price_usd": current_price,
            "market_cap_usd": market_cap,
            "total_volume_usd": total_volume,
            "variacao_pct_24h": variacao_pct_24h,
            "tendencia_24h": _classificar_variacao(variacao_pct_24h),
            "high_liquidity": bool(total_volume is not None and total_volume > HIGH_LIQUIDITY_VOLUME),
            "ingestion_timestamp_utc": datetime.now(timezone.utc).isoformat(),
        }

        dedup_key = (normalized["coin_id"], normalized["timestamp"])
        if dedup_key in dedup:
            quality["deduplicados"] += 1
        dedup[dedup_key] = normalized

    normalized_rows = list(dedup.values())
    quality["registros_validos"] = len(normalized_rows)
    return normalized_rows, quality


def _normalizar_fear_greed(payload: Dict[str, Any], run_date: str) -> Dict[str, Any]:
    first = (payload.get("data") or [{}])[0]
    value = first.get("value")
    value_int = int(value) if value is not None else None
    return {
        "date": run_date,
        "fear_greed_index": value_int,
        "fear_greed_classification": first.get("value_classification"),
        "timestamp": first.get("timestamp"),
    }


def _normalizar_trending(payload: Dict[str, Any], run_date: str) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    for idx, coin in enumerate(payload.get("coins") or [], start=1):
        item = coin.get("item") or {}
        rows.append(
            {
                "date": run_date,
                "trending_rank": idx,
                "coin_id": item.get("id"),
                "name": item.get("name"),
                "symbol": item.get("symbol"),
                "market_cap_rank": item.get("market_cap_rank"),
            }
        )
    return rows


def main() -> None:
    if len(sys.argv) < 2:
        raise SystemExit("Uso: python silver.py YYYY-MM-DD")

    run_date = sys.argv[1]
    bronze_dir = _bronze_dir(run_date)
    silver_dir = _silver_dir(run_date)

    markets_path = bronze_dir / "coingecko_markets.json"
    fear_greed_path = bronze_dir / "fear_greed.json"
    trending_path = bronze_dir / "coingecko_trending.json"

    if not markets_path.exists():
        raise FileNotFoundError(f"Arquivo bronze ausente: {markets_path}")

    markets_payload = _load_json(markets_path)
    normalized_markets, quality = _normalizar_markets(markets_payload, run_date)

    _write_json(silver_dir / "market_metrics.json", normalized_markets)

    if fear_greed_path.exists():
        fear_greed_payload = _load_json(fear_greed_path)
        _write_json(silver_dir / "fear_greed.json", _normalizar_fear_greed(fear_greed_payload, run_date))

    if trending_path.exists():
        trending_payload = _load_json(trending_path)
        _write_json(silver_dir / "trending.json", _normalizar_trending(trending_payload, run_date))

    _write_json(silver_dir / "quality_report.json", quality)

    print(
        f"Silver gerada com sucesso em {silver_dir} | "
        f"entrada={quality['registros_entrada']} validos={quality['registros_validos']} "
        f"deduplicados={quality['deduplicados']}"
    )


if __name__ == "__main__":
    main()
