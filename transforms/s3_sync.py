import os
import sys
from datetime import datetime
from pathlib import Path


def _data_root() -> Path:
    preferred = Path("/opt/airflow/data")
    return preferred if preferred.exists() else Path("data")


def _dated_dir(layer: str, run_date: str) -> Path:
    dt = datetime.strptime(run_date, "%Y-%m-%d")
    return _data_root() / layer / dt.strftime("%Y") / dt.strftime("%m") / dt.strftime("%d")


def _s3_prefix(layer: str, run_date: str) -> str:
    dt = datetime.strptime(run_date, "%Y-%m-%d")
    return f"{layer}/{dt.strftime('%Y')}/{dt.strftime('%m')}/{dt.strftime('%d')}"


def _get_bucket_name() -> str:
    bucket = os.getenv("S3_BUCKET_NAME", "").strip()
    if not bucket:
        raise ValueError("S3_BUCKET_NAME nao definido no ambiente do Airflow")
    return bucket


def _s3_client():
    import boto3

    return boto3.client("s3")


def pull_bronze(run_date: str) -> None:
    bucket = _get_bucket_name()
    s3 = _s3_client()

    local_dir = _dated_dir("bronze", run_date)
    local_dir.mkdir(parents=True, exist_ok=True)

    required_files = [
        "coingecko_markets.json",
        "coingecko_trending.json",
        "fear_greed.json",
    ]

    prefix = _s3_prefix("bronze", run_date)
    for filename in required_files:
        key = f"{prefix}/{filename}"
        target = local_dir / filename
        s3.download_file(bucket, key, str(target))
        print(f"download: s3://{bucket}/{key} -> {target}")


def push_layers(run_date: str) -> None:
    bucket = _get_bucket_name()
    s3 = _s3_client()

    for layer in ["silver", "gold"]:
        local_dir = _dated_dir(layer, run_date)
        if not local_dir.exists():
            raise FileNotFoundError(f"Diretorio local ausente para upload: {local_dir}")

        prefix = _s3_prefix(layer, run_date)
        files = sorted(local_dir.glob("*.json"))
        if not files:
            raise FileNotFoundError(f"Nenhum JSON encontrado em {local_dir}")

        for file_path in files:
            key = f"{prefix}/{file_path.name}"
            s3.upload_file(str(file_path), bucket, key)
            print(f"upload: {file_path} -> s3://{bucket}/{key}")


def main() -> None:
    if len(sys.argv) != 3:
        raise SystemExit("Uso: python s3_sync.py [pull|push] YYYY-MM-DD")

    action = sys.argv[1].strip().lower()
    run_date = sys.argv[2].strip()

    if action == "pull":
        pull_bronze(run_date)
        return

    if action == "push":
        push_layers(run_date)
        return

    raise SystemExit("Acao invalida. Use pull ou push")


if __name__ == "__main__":
    main()
