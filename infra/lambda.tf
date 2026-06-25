# 1. Zipa o arquivo extractor.py automaticamente antes do deploy
data "archive_file" "lambda_source" {
  type        = "zip"
  source_file = "${path.module}/../lambda/extractor.py"
  output_path = "${path.module}/../lambda/extractor.zip"
}

# 2. IAM Role restrita para a Lambda de Ingestão
resource "aws_iam_role" "lambda_extraction_role" {
  name = "${var.project_name}-lambda-role"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Action    = "sts:AssumeRole"
      Effect    = "Allow"
      Principal = { Service = "lambda.amazonaws.com" }
    }]
  })
}

# Política concedendo permissão para gravar no S3 do projeto e criar logs no CloudWatch
resource "aws_iam_policy" "lambda_s3_cw_policy" {
  name = "${var.project_name}-lambda-policy"
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect   = "Allow"
        Action   = ["s3:PutObject", "s3:GetObject"]
        Resource = "${aws_s3_bucket.cham_crypto_data_lake.arn}/*"
      },
      {
        Effect   = "Allow"
        Action   = [
          "logs:CreateLogGroup",
          "logs:CreateLogStream",
          "logs:PutLogEvents"
        ]
        Resource = "arn:aws:logs:*:*:*"
      }
    ]
  })
}

resource "aws_iam_role_policy_attachment" "lambda_attach" {
  role       = aws_iam_role.lambda_extraction_role.name
  policy_arn = aws_iam_policy.lambda_s3_cw_policy.arn
}

# 3. Criação da Função Lambda na AWS
resource "aws_lambda_function" "crypto_extractor" {
  filename         = data.archive_file.lambda_source.output_path
  function_name    = "crypto_data_extractor_native"
  role             = aws_iam_role.lambda_extraction_role.arn
  handler          = "extractor.lambda_handler"
  runtime          = "python3.9"
  timeout          = 45
  source_code_hash = data.archive_file.lambda_source.output_base64sha256

  environment {
    variables = {
      S3_BUCKET_NAME = aws_s3_bucket.cham_crypto_data_lake.bucket
    }
  }
}

resource "aws_cloudwatch_event_rule" "daily_cron" {
  name                = "${var.project_name}-daily-extraction"
  description         = "Dispara a extração de criptomoedas a cada 5 minutos"
  schedule_expression = "rate(5 minutes)"
}

resource "aws_cloudwatch_event_target" "trigger_lambda" {
  rule      = aws_cloudwatch_event_rule.daily_cron.name
  target_id = "TriggerCryptoLambda"
  arn       = aws_lambda_function.crypto_extractor.arn
}

resource "aws_lambda_permission" "allow_eventbridge" {
  statement_id  = "AllowExecutionFromEventBridge"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.crypto_extractor.function_name
  principal     = "events.amazonaws.com"
  source_arn    = aws_cloudwatch_event_rule.daily_cron.arn
}