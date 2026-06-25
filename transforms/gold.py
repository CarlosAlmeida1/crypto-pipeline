import json
import sys
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from statistics import mean
from typing import Any, Dict, List


def _data_root() -> Path:
    preferred = Path("/opt/airflow/data")
    return preferred if preferred.exists() else Path("data")


def _load_json(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def _write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=True, indent=2)


def _silver_dir(run_date: str) -> Path:
    dt = datetime.strptime(run_date, "%Y-%m-%d")
    return _data_root() / "silver" / dt.strftime("%Y") / dt.strftime("%m") / dt.strftime("%d")


def _gold_dir(run_date: str) -> Path:
    dt = datetime.strptime(run_date, "%Y-%m-%d")
    return _data_root() / "gold" / dt.strftime("%Y") / dt.strftime("%m") / dt.strftime("%d")


def _load_historical_market_metrics() -> List[Dict[str, Any]]:
    base = _data_root() / "silver"
    rows: List[Dict[str, Any]] = []
    if not base.exists():
        return rows

    for metrics_file in sorted(base.glob("*/*/*/market_metrics.json")):
        payload = _load_json(metrics_file)
        if isinstance(payload, list):
            rows.extend(payload)
    return rows


def _moving_average_7d(history: List[Dict[str, Any]], run_date: str) -> List[Dict[str, Any]]:
    by_coin: Dict[str, List[Dict[str, Any]]] = defaultdict(list)

    for row in history:
        coin_id = row.get("coin_id")
        ts = row.get("timestamp")
        price = row.get("price_usd")
        if not coin_id or ts is None or price is None:
            continue
        by_coin[coin_id].append(row)

    result: List[Dict[str, Any]] = []
    for coin_id, rows in by_coin.items():
        rows_sorted = sorted(rows, key=lambda r: r.get("timestamp", ""))
        last_7 = [r.get("price_usd") for r in rows_sorted[-7:] if isinstance(r.get("price_usd"), (int, float))]
        if not last_7:
            continue
        latest = rows_sorted[-1]
        result.append(
            {
                "date": run_date,
                "coin_id": coin_id,
                "symbol": latest.get("symbol"),
                "name": latest.get("name"),
                "price_usd_latest": latest.get("price_usd"),
                "media_movel_7d_usd": round(mean(last_7), 8),
                "observacoes": len(last_7),
            }
        )
    return sorted(result, key=lambda r: r["coin_id"])


def _top_10_market_cap(current_market: List[Dict[str, Any]], run_date: str) -> List[Dict[str, Any]]:
    valid = [r for r in current_market if isinstance(r.get("market_cap_usd"), (int, float))]
    ranked = sorted(valid, key=lambda r: r["market_cap_usd"], reverse=True)[:10]
    result = []
    for idx, row in enumerate(ranked, start=1):
        result.append(
            {
                "date": run_date,
                "rank": idx,
                "coin_id": row.get("coin_id"),
                "symbol": row.get("symbol"),
                "name": row.get("name"),
                "market_cap_usd": row.get("market_cap_usd"),
                "price_usd": row.get("price_usd"),
                "variacao_pct_24h": row.get("variacao_pct_24h"),
            }
        )
    return result


def _fear_greed_cross(current_market: List[Dict[str, Any]], fear_greed: Dict[str, Any], run_date: str) -> Dict[str, Any]:
    index = fear_greed.get("fear_greed_index") if isinstance(fear_greed, dict) else None
    if not isinstance(index, int):
        return {
            "date": run_date,
            "fear_greed_index": None,
            "condicao_mercado": "indisponivel",
            "moedas_em_alta": [],
        }

    em_alta = []
    if index < 25:
        for row in current_market:
            if isinstance(row.get("variacao_pct_24h"), (int, float)) and row["variacao_pct_24h"] > 0:
                em_alta.append(
                    {
                        "coin_id": row.get("coin_id"),
                        "symbol": row.get("symbol"),
                        "name": row.get("name"),
                        "variacao_pct_24h": row.get("variacao_pct_24h"),
                    }
                )

    return {
        "date": run_date,
        "fear_greed_index": index,
        "condicao_mercado": "medo_extremo" if index < 25 else "normal_ou_otimista",
        "moedas_em_alta": sorted(em_alta, key=lambda r: r["variacao_pct_24h"], reverse=True),
    }


def _hype_vs_realidade(current_market: List[Dict[str, Any]], trending: List[Dict[str, Any]], run_date: str) -> List[Dict[str, Any]]:
    var_sorted = sorted(
        [r for r in current_market if isinstance(r.get("variacao_pct_24h"), (int, float))],
        key=lambda r: r["variacao_pct_24h"],
        reverse=True,
    )
    variacao_rank = {row.get("coin_id"): idx for idx, row in enumerate(var_sorted, start=1)}
    market_lookup = {row.get("coin_id"): row for row in current_market}

    output: List[Dict[str, Any]] = []
    for t in trending:
        coin_id = t.get("coin_id")
        if not coin_id:
            continue
        market = market_lookup.get(coin_id, {})
        trend_rank = t.get("trending_rank")
        real_rank = variacao_rank.get(coin_id)
        gap = None
        if isinstance(trend_rank, int) and isinstance(real_rank, int):
            gap = real_rank - trend_rank

        output.append(
            {
                "date": run_date,
                "coin_id": coin_id,
                "name": t.get("name") or market.get("name"),
                "symbol": t.get("symbol") or market.get("symbol"),
                "trending_rank": trend_rank,
                "rank_variacao_real": real_rank,
                "variacao_pct_24h": market.get("variacao_pct_24h"),
                "hype_vs_realidade_gap": gap,
            }
        )

    return sorted(output, key=lambda r: (r.get("trending_rank") or 9999))


def main() -> None:
    if len(sys.argv) < 2:
        raise SystemExit("Uso: python gold.py YYYY-MM-DD")

    run_date = sys.argv[1]
    silver_dir = _silver_dir(run_date)
    gold_dir = _gold_dir(run_date)

    market_path = silver_dir / "market_metrics.json"
    fear_greed_path = silver_dir / "fear_greed.json"
    trending_path = silver_dir / "trending.json"

    if not market_path.exists():
        raise FileNotFoundError(f"Arquivo silver ausente: {market_path}")

    current_market = _load_json(market_path)
    fear_greed = _load_json(fear_greed_path) if fear_greed_path.exists() else {}
    trending = _load_json(trending_path) if trending_path.exists() else []

    historical_market = _load_historical_market_metrics()

    top_10 = _top_10_market_cap(current_market, run_date)
    ma7 = _moving_average_7d(historical_market, run_date)
    fear_cross = _fear_greed_cross(current_market, fear_greed, run_date)
    hype = _hype_vs_realidade(current_market, trending, run_date)

    _write_json(gold_dir / "top10_market_cap.json", top_10)
    _write_json(gold_dir / "media_movel_7d.json", ma7)
    _write_json(gold_dir / "fear_greed_cross.json", fear_cross)
    _write_json(gold_dir / "hype_vs_realidade.json", hype)

    summary = {
        "date": run_date,
        "top10_count": len(top_10),
        "media_movel_7d_count": len(ma7),
        "hype_vs_realidade_count": len(hype),
    }
    _write_json(gold_dir / "summary.json", summary)

    print(
        f"Gold gerada com sucesso em {gold_dir} | "
        f"top10={len(top_10)} ma7={len(ma7)} hype={len(hype)}"
    )


if __name__ == "__main__":
    main()
