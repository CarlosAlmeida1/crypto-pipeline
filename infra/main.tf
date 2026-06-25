terraform {
  required_version = ">= 1.0.0"
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
    random = {
      source  = "hashicorp/random"
      version = "~> 3.0"
    }
    archive = {
      source  = "hashicorp/archive"
      version = "~> 2.0"
    }
  }
}

provider "aws" {
  region = var.aws_region
}

# Gerador de sufixo aleatório para evitar colisão de nomes no S3
resource "random_id" "bucket_suffix" {
  byte_length = 4
}

# --- REDE E SEGURANÇA PARA O AIRFLOW ---
resource "aws_security_group" "airflow_sg" {
  name        = "${var.project_name}-airflow-sg"
  description = "Permite acesso Web ao Airflow (8080) e SSH (22)"

  ingress {
    from_port   = 8080
    to_port     = 8080
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"] # Interface Web do Airflow
  }

  ingress {
    from_port   = 22
    to_port     = 22
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"] # Acesso SSH para manutenção se necessário
  }

  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }
}

# --- PERMISSÕES DA EC2 (AIRFLOW) ---
resource "aws_iam_role" "ec2_airflow_role" {
  name = "${var.project_name}-ec2-airflow-role"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Action    = "sts:AssumeRole"
      Effect    = "Allow"
      Principal = { Service = "ec2.amazonaws.com" }
    }]
  })
}

resource "aws_iam_role_policy_attachment" "ec2_s3_attach" {
  role       = aws_iam_role.ec2_airflow_role.name
  policy_arn = "arn:aws:iam::aws:policy/AmazonS3FullAccess"
}

resource "aws_iam_instance_profile" "ec2_profile" {
  name = "${var.project_name}-ec2-profile"
  role = aws_iam_role.ec2_airflow_role.name
}

# --- INSTÂNCIA EC2 (SERVIDOR DO AIRFLOW) ---
resource "aws_instance" "airflow_server" {
  ami                  = "ami-0c7217cdde317cfec" # Ubuntu 22.04 LTS em us-east-1
  instance_type        = var.airflow_instance_type
  security_groups      = [aws_security_group.airflow_sg.name]
  iam_instance_profile = aws_iam_instance_profile.ec2_profile.name

  # Inicialização automática do Apache Airflow Standalone na AWS
  user_data = <<-EOF
              #!/bin/bash
              apt-get update -y
              apt-get install -y python3-pip python3-venv libpq-dev
              
              export AIRFLOW_HOME=/home/ubuntu/airflow
              pip3 install "apache-airflow[amazon,pandas]==2.7.1" --constraint "https://raw.githubusercontent.com/apache/airflow/constraints-2.7.1/constraints-3.10.txt"
              
              airflow db init
              airflow users create --username admin --firstname Crypto --lastname Admin --role Admin --email admin@crypto.com --password admin
              
              airflow webserver --port 8080 -D
              airflow scheduler -D
              EOF

  tags = {
    Name = "Airflow-${var.project_name}-Server"
  }
}

# Output para exibir o link de acesso direto no terminal após o apply
output "airflow_public_url" {
  value       = "http://${aws_instance.airflow_server.public_ip}:8080"
  description = "Acesse a interface Web do Airflow na AWS por este link"
}