resource "aws_s3_bucket" "cham_crypto_data_lake" {
    bucket = "${var.project_name}-datalake-${random_id.bucket_suffix.hex}"
    force_destroy = true
}

resource "aws_s3_bucket_public_access_block" "cham_datalake_privacy" {
    bucket = aws_s3_bucket.cham_crypto_data_lake.id
    block_public_acls = true
    block_public_policy = true
    ignore_public_acls = true
    restrict_public_buckets = true
}

output "s3_bucket_name" {
    value = aws_s3_bucket.cham_crypto_data_lake.bucket
    description = "Nome do bucket S3 criado para o data lake"
}
