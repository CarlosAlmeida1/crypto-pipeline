from airflow import DAG
from airflow.providers.standard.operators.empty import EmptyOperator
from airflow.providers.standard.operators.bash import BashOperator
from datetime import datetime, timedelta

# Argumentos padrão da DAG
default_args = {
    'owner': 'data_engineer',
    'depends_on_past': False,
    'start_date': datetime(2023, 10, 1),
    'email_on_failure': False,
    'email_on_retry': False,
    'retries': 1,
    'retry_delay': timedelta(minutes=5),
}

with DAG(
    'crypto_market_pipeline',
    default_args=default_args,
    description='Pipeline ETL para mercado de criptomoedas (Bronze -> Silver -> Gold)',
    schedule='0 1 * * *',
    catchup=False,
    tags=['crypto', 'etl'],
) as dag:

    extract = EmptyOperator(
        task_id='extract'
    )

    sync_bronze_from_s3 = BashOperator(
        task_id='sync_bronze_from_s3',
        bash_command='python /opt/airflow/transforms/s3_sync.py pull {{ ds }}'
    )

    transform_silver = BashOperator(
        task_id='transform_bronze_to_silver',
        bash_command='python /opt/airflow/transforms/silver.py {{ ds }}'
    )

    transform_gold = BashOperator(
        task_id='transform_silver_to_gold',
        bash_command='python /opt/airflow/transforms/gold.py {{ ds }}'
    )

    sync_silver_gold_to_s3 = BashOperator(
        task_id='sync_silver_gold_to_s3',
        bash_command='python /opt/airflow/transforms/s3_sync.py push {{ ds }}'
    )

    data_quality_check = EmptyOperator(
        task_id='check_data_quality'
    )

    extract >> sync_bronze_from_s3 >> transform_silver >> transform_gold >> sync_silver_gold_to_s3 >> data_quality_check