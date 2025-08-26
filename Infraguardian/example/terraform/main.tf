terraform {
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = ">= 5.0"
    }
  }
}

provider "aws" {
  region = "us-east-1"
}

# Intentional issues for scanners to catch:
# - S3 bucket without default encryption or public access block
# - Multiple NAT gateways (cost)

resource "aws_s3_bucket" "data" {
  bucket = var.bucket_name
}

resource "aws_nat_gateway" "nat" {
  count         = var.nat_gateway_count
  allocation_id = "eipalloc-00000000"   # placeholder id
  subnet_id     = "subnet-00000000"     # placeholder id
}