variable "aws_region" {
  type        = string
  default     = "us-east-1"
  description = "Região da AWS onde a infraestrutura será provisionada"
}

variable "project_name" {
  type        = string
  default     = "crypto-pipeline"
  description = "Nome base para os recursos do projeto"
}

variable "airflow_instance_type" {
  type        = string
  default     = "t3.medium"
  description = "Tamanho da instância EC2 para rodar o Airflow"
}