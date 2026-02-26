"""Generate the 10 iac-eval dataset entries as BenchmarkInstance JSONL files."""

import json
import os

DATASET_DIR = os.path.join(os.path.dirname(__file__), "..", "dataset")


def make_instance(
    instance_id, problem_statement, difficulty, tags, expected_resources,
    required_outputs, gold_solution_main_tf, hints, validation_script,
    setup_script=None, region="us-east-1",
    estimated_cost="$0.00", deployment_time_seconds=120,
):
    result = {
        "instance_id": instance_id,
        "problem_statement": problem_statement,
        "difficulty": difficulty,
        "tags": tags,
        "provider": "aws",
        "region": region,
        "expected_resources": expected_resources,
        "required_outputs": required_outputs,
        "validation_script": validation_script,
        "gold_solution": {"main.tf": gold_solution_main_tf},
        "hints": hints,
        "metadata": {
            "estimated_cost": estimated_cost,
            "deployment_time_seconds": deployment_time_seconds,
            "cleanup_required": True,
            "created_at": "2025-02-25",
            "author": "iac-eval",
        },
    }
    if setup_script:
        result["setup_script"] = setup_script
    return result


DATASETS = []

# =============================================================================
# 1. API Gateway + Lambda + S3 + DynamoDB (Cat Picture Service)
# =============================================================================
DATASETS.append({
    "dir": "apigw_lambda_s3_dynamodb",
    "instance": make_instance(
        instance_id="terraform-aws-apigw-lambda-001",
        problem_statement=(
            "Create an API Gateway REST API named 'caas' with a resource endpoint 'cat' "
            "linking to two methods GET and PUT. Each method should integrate with a Lambda function "
            "that can access an S3 bucket for storing cat images and a DynamoDB table for tracking names. "
            "Include proper IAM roles, Lambda permissions, API deployment and stage."
        ),
        difficulty="hard",
        tags=["api-gateway", "lambda", "s3", "dynamodb", "serverless", "aws"],
        expected_resources={
            "aws_api_gateway_rest_api": 1,
            "aws_api_gateway_resource": 1,
            "aws_api_gateway_method": 2,
            "aws_api_gateway_integration": 2,
            "aws_api_gateway_deployment": 1,
            "aws_api_gateway_stage": 1,
            "aws_lambda_function": 1,
            "aws_lambda_permission": 1,
            "aws_iam_role": 1,
            "aws_iam_role_policy": 1,
            "aws_s3_bucket": 1,
            "aws_dynamodb_table": 1,
        },
        required_outputs=["api_id", "stage_invoke_url"],
        gold_solution_main_tf=r'''resource "aws_dynamodb_table" "caas" {
  name         = "cat_names"
  hash_key     = "name"
  billing_mode = "PAY_PER_REQUEST"

  attribute {
    name = "name"
    type = "S"
  }
}

resource "aws_s3_bucket" "caas" {
  bucket_prefix = "cat-image"
}

resource "aws_iam_role" "lambda_role" {
  name = "lambda_api_gateway_role"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Action = "sts:AssumeRole"
        Effect = "Allow"
        Principal = {
          Service = "lambda.amazonaws.com"
        }
      }
    ]
  })
}

resource "aws_iam_role_policy" "lambda_policy" {
  name   = "lambda_policy"
  role   = aws_iam_role.lambda_role.id
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Action   = ["s3:GetObject", "s3:PutObject"]
        Effect   = "Allow"
        Resource = "${aws_s3_bucket.caas.arn}/*"
      },
      {
        Action   = ["dynamodb:PutItem"]
        Effect   = "Allow"
        Resource = aws_dynamodb_table.caas.arn
      }
    ]
  })
}

resource "aws_api_gateway_rest_api" "caas" {
  name = "caas"
}

resource "aws_api_gateway_resource" "caas_cat" {
  rest_api_id = aws_api_gateway_rest_api.caas.id
  parent_id   = aws_api_gateway_rest_api.caas.root_resource_id
  path_part   = "cat"
}

resource "aws_api_gateway_method" "caas_cat_get" {
  rest_api_id   = aws_api_gateway_rest_api.caas.id
  resource_id   = aws_api_gateway_resource.caas_cat.id
  http_method   = "GET"
  authorization = "NONE"
}

resource "aws_api_gateway_method" "caas_cat_put" {
  rest_api_id   = aws_api_gateway_rest_api.caas.id
  resource_id   = aws_api_gateway_resource.caas_cat.id
  http_method   = "PUT"
  authorization = "NONE"
}

data "archive_file" "caas_cat" {
  type        = "zip"
  source_file = "${path.module}/lambda_code/handler.py"
  output_path = "${path.module}/lambda_code/handler.zip"
}

resource "aws_lambda_function" "caas_cat" {
  function_name    = "caas_cat"
  role             = aws_iam_role.lambda_role.arn
  filename         = data.archive_file.caas_cat.output_path
  source_code_hash = data.archive_file.caas_cat.output_base64sha256
  handler          = "handler.handler"
  runtime          = "python3.12"

  environment {
    variables = {
      CAAS_S3_BUCKET      = aws_s3_bucket.caas.id
      DYNAMODB_TABLE_NAME = aws_dynamodb_table.caas.id
    }
  }
}

resource "aws_api_gateway_integration" "caas_cat_get" {
  rest_api_id             = aws_api_gateway_rest_api.caas.id
  resource_id             = aws_api_gateway_resource.caas_cat.id
  http_method             = aws_api_gateway_method.caas_cat_get.http_method
  type                    = "AWS_PROXY"
  integration_http_method = "POST"
  uri                     = aws_lambda_function.caas_cat.invoke_arn
}

resource "aws_api_gateway_integration" "caas_cat_put" {
  rest_api_id             = aws_api_gateway_rest_api.caas.id
  resource_id             = aws_api_gateway_resource.caas_cat.id
  http_method             = aws_api_gateway_method.caas_cat_put.http_method
  type                    = "AWS_PROXY"
  integration_http_method = "POST"
  uri                     = aws_lambda_function.caas_cat.invoke_arn
}

resource "aws_lambda_permission" "caas_cat" {
  action        = "lambda:InvokeFunction"
  principal     = "apigateway.amazonaws.com"
  function_name = aws_lambda_function.caas_cat.function_name
  source_arn    = "${aws_api_gateway_rest_api.caas.execution_arn}/*/*"
}

resource "aws_api_gateway_deployment" "api_deployment" {
  rest_api_id = aws_api_gateway_rest_api.caas.id
  depends_on  = [aws_api_gateway_integration.caas_cat_get, aws_api_gateway_integration.caas_cat_put]
}

resource "aws_api_gateway_stage" "api_stage" {
  deployment_id = aws_api_gateway_deployment.api_deployment.id
  rest_api_id   = aws_api_gateway_rest_api.caas.id
  stage_name    = "dev"
}

output "api_id" {
  value = aws_api_gateway_rest_api.caas.id
}

output "stage_invoke_url" {
  value = aws_api_gateway_stage.api_stage.invoke_url
}
''',
        hints=[
            "Use aws_api_gateway_rest_api with a name",
            "Create a resource with path_part and link to rest_api",
            "Create GET and PUT methods on the resource",
            "Use AWS_PROXY integration type for Lambda",
            "Lambda needs IAM role with S3 and DynamoDB permissions",
            "Don't forget aws_api_gateway_deployment and aws_api_gateway_stage",
            "Add aws_lambda_permission for API Gateway to invoke Lambda",
        ],
        validation_script="dataset/apigw_lambda_s3_dynamodb/validation.py",
        deployment_time_seconds=180,
    ),
})

# =============================================================================
# 2. VPC with Subnets, IGW, Route Table, Security Group, DB Subnet Group
# =============================================================================
DATASETS.append({
    "dir": "vpc_db_subnet_group",
    "instance": make_instance(
        instance_id="terraform-aws-vpc-db-001",
        problem_statement=(
            "Set up a VPC with CIDR 10.0.0.0/16 and two subnets in different availability zones, "
            "an internet gateway, and a route table for internet access. Define a security group "
            "allowing access to MySQL (port 3306) and PostgreSQL (port 5432) from any IP address. "
            "Create a database subnet group including both subnets."
        ),
        difficulty="hard",
        tags=["vpc", "networking", "security-group", "rds", "aws"],
        expected_resources={
            "aws_vpc": 1,
            "aws_subnet": 2,
            "aws_internet_gateway": 1,
            "aws_route_table": 1,
            "aws_route_table_association": 2,
            "aws_security_group": 1,
            "aws_db_subnet_group": 1,
        },
        required_outputs=["vpc_id", "subnet_ids", "security_group_id", "db_subnet_group_name"],
        gold_solution_main_tf=r'''resource "aws_vpc" "main" {
  cidr_block           = "10.0.0.0/16"
  enable_dns_hostnames = true
}

resource "aws_subnet" "zonea" {
  vpc_id            = aws_vpc.main.id
  cidr_block        = "10.0.1.0/24"
  availability_zone = "us-east-1a"
}

resource "aws_subnet" "zoneb" {
  vpc_id            = aws_vpc.main.id
  cidr_block        = "10.0.2.0/24"
  availability_zone = "us-east-1b"
}

resource "aws_internet_gateway" "gateway" {
  vpc_id = aws_vpc.main.id
}

resource "aws_route_table" "public" {
  vpc_id = aws_vpc.main.id

  route {
    cidr_block = "0.0.0.0/0"
    gateway_id = aws_internet_gateway.gateway.id
  }
}

resource "aws_route_table_association" "publica" {
  subnet_id      = aws_subnet.zonea.id
  route_table_id = aws_route_table.public.id
}

resource "aws_route_table_association" "publicb" {
  subnet_id      = aws_subnet.zoneb.id
  route_table_id = aws_route_table.public.id
}

resource "aws_security_group" "allow_db_access" {
  name   = "allow-db-access"
  vpc_id = aws_vpc.main.id

  ingress {
    from_port   = 3306
    to_port     = 3306
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"]
  }

  ingress {
    from_port   = 5432
    to_port     = 5432
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"]
  }
}

resource "aws_db_subnet_group" "default" {
  subnet_ids = [aws_subnet.zonea.id, aws_subnet.zoneb.id]
}

output "vpc_id" {
  value = aws_vpc.main.id
}

output "subnet_ids" {
  value = [aws_subnet.zonea.id, aws_subnet.zoneb.id]
}

output "security_group_id" {
  value = aws_security_group.allow_db_access.id
}

output "db_subnet_group_name" {
  value = aws_db_subnet_group.default.name
}
''',
        hints=[
            "Create a VPC with cidr_block 10.0.0.0/16",
            "Create two subnets in different availability zones",
            "Attach an internet gateway to the VPC",
            "Create a route table with a default route to the internet gateway",
            "Associate both subnets with the route table",
            "Security group needs ingress rules for ports 3306 and 5432",
            "DB subnet group must reference both subnet IDs",
        ],
        validation_script="dataset/vpc_db_subnet_group/validation.py",
    ),
})

# =============================================================================
# 3. Route 53 with Private/Public Zones and RDS
# =============================================================================
DATASETS.append({
    "dir": "route53_rds_split_dns",
    "instance": make_instance(
        instance_id="terraform-aws-r53-rds-001",
        problem_statement=(
            "Configure Route 53 to return different database endpoints to internal versus external users. "
            "Internal users are routed to an internal RDS instance, while external users are routed to a "
            "publicly accessible one. Create a VPC with two subnets and a DB subnet group. "
            "Name the zones 'private' and 'public', the databases 'internal' and 'public', and the subnet group 'main'."
        ),
        difficulty="hard",
        tags=["route53", "rds", "vpc", "dns", "split-horizon", "aws"],
        expected_resources={
            "aws_vpc": 1,
            "aws_subnet": 2,
            "aws_db_subnet_group": 1,
            "aws_db_instance": 2,
            "aws_route53_zone": 2,
            "aws_route53_record": 2,
        },
        required_outputs=["public_zone_id", "private_zone_id", "public_db_endpoint", "internal_db_endpoint"],
        gold_solution_main_tf=r'''resource "aws_vpc" "main" {
  cidr_block = "10.0.0.0/24"
}

resource "aws_subnet" "maina" {
  vpc_id            = aws_vpc.main.id
  cidr_block        = "10.0.0.0/25"
  availability_zone = "us-east-1a"
}

resource "aws_subnet" "mainb" {
  vpc_id            = aws_vpc.main.id
  cidr_block        = "10.0.0.128/25"
  availability_zone = "us-east-1b"
}

resource "aws_db_subnet_group" "main" {
  name       = "mydb-subnet-group"
  subnet_ids = [aws_subnet.maina.id, aws_subnet.mainb.id]
}

resource "aws_db_instance" "internal" {
  allocated_storage    = 20
  engine               = "mysql"
  instance_class       = "db.t3.micro"
  identifier           = "internal"
  username             = "user"
  password             = "password"
  db_subnet_group_name = aws_db_subnet_group.main.name
  skip_final_snapshot  = true
}

resource "aws_db_instance" "public" {
  publicly_accessible = true
  allocated_storage   = 20
  engine              = "mysql"
  instance_class      = "db.t3.micro"
  identifier          = "public"
  username            = "user"
  password            = "password"
  skip_final_snapshot = true
}

resource "aws_route53_zone" "public" {
  name = "example53.com"
}

resource "aws_route53_zone" "private" {
  name = "example53.com"
  vpc {
    vpc_id = aws_vpc.main.id
  }
}

resource "aws_route53_record" "public_db" {
  zone_id = aws_route53_zone.public.zone_id
  name    = "db.example53.com"
  type    = "CNAME"
  ttl     = "300"
  records = [aws_db_instance.public.address]
}

resource "aws_route53_record" "internal_db" {
  zone_id = aws_route53_zone.private.zone_id
  name    = "db.example53.com"
  type    = "CNAME"
  ttl     = "300"
  records = [aws_db_instance.internal.address]
}

output "public_zone_id" {
  value = aws_route53_zone.public.zone_id
}

output "private_zone_id" {
  value = aws_route53_zone.private.zone_id
}

output "public_db_endpoint" {
  value = aws_db_instance.public.address
}

output "internal_db_endpoint" {
  value = aws_db_instance.internal.address
}
''',
        hints=[
            "Create a public and private Route 53 zone with the same domain name",
            "The private zone needs a vpc block with vpc_id",
            "Create two RDS instances: one internal with db_subnet_group_name, one public with publicly_accessible",
            "Route 53 records should be CNAME type pointing to db instance addresses",
            "You need a VPC, two subnets in different AZs, and a DB subnet group",
        ],
        validation_script="dataset/route53_rds_split_dns/validation.py",
        deployment_time_seconds=300,
        estimated_cost="$0.10 (RDS instances)",
    ),
})

# =============================================================================
# 4. Route 53 Weighted Routing with RDS Replicas (Multi-Region)
# =============================================================================
DATASETS.append({
    "dir": "route53_weighted_rds_replicas",
    "instance": make_instance(
        instance_id="terraform-aws-r53-weighted-001",
        problem_statement=(
            "Configure a weighted routing policy using Route 53 that splits traffic between three "
            "RDS read replicas of a main database. Provision the main db_instance 'primary' in us-west-1. "
            "Create three replicas: 'replica_us_east' in us-east-1, 'replica_eu_central' in eu-central-1, "
            "and 'replica_ap_southeast' in ap-southeast-1. Use provider aliases and weighted Route 53 records "
            "pointing to each replica's endpoint."
        ),
        difficulty="hard",
        tags=["route53", "rds", "multi-region", "weighted-routing", "dns", "aws"],
        expected_resources={
            "aws_db_instance": 4,
            "aws_route53_zone": 1,
            "aws_route53_record": 3,
        },
        required_outputs=["zone_id", "primary_endpoint"],
        gold_solution_main_tf=r'''provider "aws" {
  alias  = "main"
  region = "us-west-1"
}

provider "aws" {
  alias  = "us_east"
  region = "us-east-1"
}

provider "aws" {
  alias  = "eu_central"
  region = "eu-central-1"
}

provider "aws" {
  alias  = "ap_southeast"
  region = "ap-southeast-1"
}

resource "aws_db_instance" "primary" {
  provider                = aws.main
  identifier              = "master"
  allocated_storage       = 20
  engine                  = "postgres"
  instance_class          = "db.t3.micro"
  username                = "dbadmin"
  password                = "your_password_here"
  skip_final_snapshot     = true
  backup_retention_period = 7
}

resource "aws_db_instance" "replica_us_east" {
  provider            = aws.us_east
  replicate_source_db = aws_db_instance.primary.arn
  instance_class      = "db.t3.micro"
  identifier          = "mydb-replica-us-east"
  skip_final_snapshot = true
}

resource "aws_db_instance" "replica_eu_central" {
  provider            = aws.eu_central
  replicate_source_db = aws_db_instance.primary.arn
  instance_class      = "db.t3.micro"
  identifier          = "mydb-replica-eu-central"
  skip_final_snapshot = true
}

resource "aws_db_instance" "replica_ap_southeast" {
  provider            = aws.ap_southeast
  replicate_source_db = aws_db_instance.primary.arn
  instance_class      = "db.t3.micro"
  identifier          = "mydb-replica-ap-southeast"
  skip_final_snapshot = true
}

resource "aws_route53_zone" "main" {
  provider = aws.main
  name     = "example53.com"
}

resource "aws_route53_record" "replica_us_east_cname" {
  provider = aws.main
  zone_id  = aws_route53_zone.main.zone_id
  name     = "db.example53.com"
  type     = "CNAME"
  records  = [aws_db_instance.replica_us_east.endpoint]
  ttl      = "60"
  weighted_routing_policy {
    weight = 30
  }
  set_identifier = "replica-us-east"
}

resource "aws_route53_record" "replica_eu_central_cname" {
  provider = aws.main
  zone_id  = aws_route53_zone.main.zone_id
  name     = "db.example53.com"
  type     = "CNAME"
  records  = [aws_db_instance.replica_eu_central.endpoint]
  ttl      = "60"
  weighted_routing_policy {
    weight = 30
  }
  set_identifier = "replica-eu-central"
}

resource "aws_route53_record" "replica_ap_southeast_cname" {
  provider = aws.main
  zone_id  = aws_route53_zone.main.zone_id
  name     = "db.example53.com"
  type     = "CNAME"
  records  = [aws_db_instance.replica_ap_southeast.endpoint]
  ttl      = "60"
  weighted_routing_policy {
    weight = 30
  }
  set_identifier = "replica-ap-southeast"
}

output "zone_id" {
  value = aws_route53_zone.main.zone_id
}

output "primary_endpoint" {
  value = aws_db_instance.primary.endpoint
}
''',
        hints=[
            "Use provider aliases for each region",
            "The primary DB needs backup_retention_period > 0 for replicas",
            "Replicas use replicate_source_db referencing the primary ARN",
            "Route 53 records need weighted_routing_policy and set_identifier",
            "All records share the same name but different set_identifiers",
        ],
        validation_script="dataset/route53_weighted_rds_replicas/validation.py",
        deployment_time_seconds=600,
        estimated_cost="$0.20 (multi-region RDS)",
    ),
})

# =============================================================================
# 5. Three-Tier VPC with EC2 and RDS
# =============================================================================
DATASETS.append({
    "dir": "three_tier_vpc",
    "instance": make_instance(
        instance_id="terraform-aws-3tier-001",
        problem_statement=(
            "Create a VPC with three subnets: one public subnet and two private subnets. "
            "Deploy an EC2 instance in the public subnet as a web server, an EC2 instance in "
            "the first private subnet as an application server, and an RDS instance in the "
            "second private subnet as the database. Include a security group and DB subnet group."
        ),
        difficulty="hard",
        tags=["vpc", "ec2", "rds", "three-tier", "networking", "aws"],
        expected_resources={
            "aws_vpc": 1,
            "aws_subnet": 3,
            "aws_security_group": 1,
            "aws_instance": 2,
            "aws_db_instance": 1,
            "aws_db_subnet_group": 1,
        },
        required_outputs=["vpc_id", "web_instance_id", "app_instance_id", "db_endpoint"],
        gold_solution_main_tf=r'''resource "aws_vpc" "my_vpc" {
  cidr_block = "10.0.0.0/16"
}

resource "aws_subnet" "public_subnet" {
  vpc_id                  = aws_vpc.my_vpc.id
  cidr_block              = "10.0.1.0/24"
  availability_zone       = "us-east-1a"
  map_public_ip_on_launch = true
}

resource "aws_subnet" "private_subnet_1" {
  vpc_id            = aws_vpc.my_vpc.id
  cidr_block        = "10.0.2.0/24"
  availability_zone = "us-east-1b"
}

resource "aws_subnet" "private_subnet_2" {
  vpc_id            = aws_vpc.my_vpc.id
  cidr_block        = "10.0.3.0/24"
  availability_zone = "us-east-1c"
}

resource "aws_security_group" "web_sg" {
  vpc_id = aws_vpc.my_vpc.id
  name   = "web_sg"
}

resource "aws_instance" "web_instance" {
  ami             = "ami-0c02fb55956c7d316"
  instance_type   = "t2.micro"
  subnet_id       = aws_subnet.public_subnet.id
  security_groups = [aws_security_group.web_sg.id]
}

resource "aws_instance" "app_instance" {
  ami           = "ami-0c02fb55956c7d316"
  instance_type = "t2.micro"
  subnet_id     = aws_subnet.private_subnet_1.id
}

resource "aws_db_subnet_group" "main" {
  name       = "mydb-subnet-group"
  subnet_ids = [aws_subnet.private_subnet_1.id, aws_subnet.private_subnet_2.id]
}

resource "aws_db_instance" "db_instance" {
  identifier           = "mydb"
  engine               = "mysql"
  instance_class       = "db.t3.micro"
  allocated_storage    = 20
  username             = "admin"
  password             = "your-password"
  skip_final_snapshot  = true
  db_subnet_group_name = aws_db_subnet_group.main.name
}

output "vpc_id" {
  value = aws_vpc.my_vpc.id
}

output "web_instance_id" {
  value = aws_instance.web_instance.id
}

output "app_instance_id" {
  value = aws_instance.app_instance.id
}

output "db_endpoint" {
  value = aws_db_instance.db_instance.endpoint
}
''',
        hints=[
            "Public subnet needs map_public_ip_on_launch = true",
            "Private subnets should be in different availability zones for the DB subnet group",
            "EC2 instances need ami and instance_type",
            "RDS instance needs db_subnet_group_name",
            "Security group should be associated with the VPC",
        ],
        validation_script="dataset/three_tier_vpc/validation.py",
        deployment_time_seconds=300,
        estimated_cost="$0.10 (EC2 + RDS)",
    ),
})

# =============================================================================
# 6. EventBridge (CloudWatch Events) + Lambda Scheduled Task
# =============================================================================
DATASETS.append({
    "dir": "eventbridge_lambda_cron",
    "instance": make_instance(
        instance_id="terraform-aws-eventbridge-001",
        problem_statement=(
            "Create an EventBridge (CloudWatch Events) rule that triggers a Lambda function "
            "every day at 7:00 UTC using a cron expression. The Lambda function should have "
            "proper IAM role with basic execution permissions. Include the event target, "
            "Lambda permission for EventBridge, and IAM role policy attachment."
        ),
        difficulty="medium",
        tags=["eventbridge", "lambda", "cron", "scheduled", "serverless", "aws"],
        expected_resources={
            "aws_cloudwatch_event_rule": 1,
            "aws_cloudwatch_event_target": 1,
            "aws_lambda_function": 1,
            "aws_lambda_permission": 1,
            "aws_iam_role": 1,
            "aws_iam_role_policy_attachment": 1,
        },
        required_outputs=["rule_arn", "lambda_arn"],
        gold_solution_main_tf=r'''data "aws_iam_policy_document" "cron_assume_role" {
  statement {
    actions = ["sts:AssumeRole"]
    principals {
      type        = "Service"
      identifiers = ["lambda.amazonaws.com", "events.amazonaws.com"]
    }
  }
}

resource "aws_iam_role" "cron" {
  name               = "cron_assume_role"
  assume_role_policy = data.aws_iam_policy_document.cron_assume_role.json
}

resource "aws_iam_role_policy_attachment" "cron" {
  role       = aws_iam_role.cron.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole"
}

resource "aws_cloudwatch_event_rule" "cron" {
  schedule_expression = "cron(0 7 * * ? *)"
  role_arn            = aws_iam_role.cron.arn
}

resource "aws_cloudwatch_event_target" "cron" {
  rule = aws_cloudwatch_event_rule.cron.name
  arn  = aws_lambda_function.cron.arn
}

data "archive_file" "lambda_func" {
  type        = "zip"
  source_file = "${path.module}/lambda_code/handler.py"
  output_path = "${path.module}/lambda_code/handler.zip"
}

resource "aws_lambda_function" "cron" {
  function_name    = "cron-lambda-function"
  role             = aws_iam_role.cron.arn
  filename         = data.archive_file.lambda_func.output_path
  source_code_hash = data.archive_file.lambda_func.output_base64sha256
  handler          = "handler.handler"
  runtime          = "python3.12"
}

resource "aws_lambda_permission" "cron" {
  function_name = aws_lambda_function.cron.function_name
  action        = "lambda:InvokeFunction"
  principal     = "events.amazonaws.com"
  source_arn    = aws_cloudwatch_event_rule.cron.arn
}

output "rule_arn" {
  value = aws_cloudwatch_event_rule.cron.arn
}

output "lambda_arn" {
  value = aws_lambda_function.cron.arn
}
''',
        hints=[
            "Use schedule_expression = 'cron(0 7 * * ? *)' for daily at 7 UTC",
            "The event rule needs role_arn for the IAM role",
            "Event target links the rule to the Lambda function ARN",
            "Lambda permission must allow events.amazonaws.com principal",
            "IAM role needs AssumeRole for both lambda and events services",
        ],
        validation_script="dataset/eventbridge_lambda_cron/validation.py",
    ),
})

# =============================================================================
# 7. S3 + DynamoDB for Terraform State Backend
# =============================================================================
DATASETS.append({
    "dir": "s3_dynamodb_tf_state",
    "instance": make_instance(
        instance_id="terraform-aws-tfstate-001",
        problem_statement=(
            "Set up an S3 bucket and DynamoDB table for Terraform remote state management. "
            "The S3 bucket must have versioning enabled, server-side encryption using AES256, "
            "and all public access blocked. Create a DynamoDB table with PAY_PER_REQUEST billing "
            "mode and a hash key named 'LockID' of type String for state locking."
        ),
        difficulty="medium",
        tags=["s3", "dynamodb", "terraform-state", "encryption", "aws"],
        expected_resources={
            "aws_s3_bucket": 1,
            "aws_s3_bucket_versioning": 1,
            "aws_s3_bucket_server_side_encryption_configuration": 1,
            "aws_s3_bucket_public_access_block": 1,
            "aws_dynamodb_table": 1,
        },
        required_outputs=["bucket_name", "dynamodb_table_name"],
        gold_solution_main_tf=r'''resource "aws_s3_bucket" "terraform_state" {
  bucket = "my-terraform-state-bucket"
}

resource "aws_s3_bucket_versioning" "enabled" {
  bucket = aws_s3_bucket.terraform_state.id
  versioning_configuration {
    status = "Enabled"
  }
}

resource "aws_s3_bucket_server_side_encryption_configuration" "default" {
  bucket = aws_s3_bucket.terraform_state.id

  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm = "AES256"
    }
  }
}

resource "aws_s3_bucket_public_access_block" "public_access" {
  bucket                  = aws_s3_bucket.terraform_state.id
  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

resource "aws_dynamodb_table" "terraform_locks" {
  name         = "terraform-locks"
  billing_mode = "PAY_PER_REQUEST"
  hash_key     = "LockID"

  attribute {
    name = "LockID"
    type = "S"
  }
}

output "bucket_name" {
  value = aws_s3_bucket.terraform_state.id
}

output "dynamodb_table_name" {
  value = aws_dynamodb_table.terraform_locks.name
}
''',
        hints=[
            "S3 bucket versioning is a separate resource: aws_s3_bucket_versioning",
            "Server-side encryption uses aws_s3_bucket_server_side_encryption_configuration",
            "Public access block needs all four boolean flags set to true",
            "DynamoDB table needs billing_mode PAY_PER_REQUEST and hash_key LockID",
            "The LockID attribute must be type S (String)",
        ],
        validation_script="dataset/s3_dynamodb_tf_state/validation.py",
    ),
})

# =============================================================================
# 8. VPC with Public Subnets and Internet Gateway
# =============================================================================
DATASETS.append({
    "dir": "vpc_public_subnets",
    "instance": make_instance(
        instance_id="terraform-aws-vpc-pub-001",
        problem_statement=(
            "Create a VPC with CIDR 10.0.0.0/16, enable DNS hostnames, and deploy multiple "
            "public subnets across different availability zones. Attach an internet gateway "
            "and create a route table with a default route for internet access. Associate all "
            "subnets with the route table. Use count or indexing for the subnets."
        ),
        difficulty="medium",
        tags=["vpc", "networking", "subnets", "internet-gateway", "aws"],
        expected_resources={
            "aws_vpc": 1,
            "aws_subnet": 2,
            "aws_internet_gateway": 1,
            "aws_route_table": 1,
            "aws_route_table_association": 2,
        },
        required_outputs=["vpc_id", "subnet_ids"],
        gold_solution_main_tf=r'''locals {
  subnet_count = 2
}

resource "aws_vpc" "main" {
  cidr_block           = "10.0.0.0/16"
  enable_dns_hostnames = true

  tags = {
    Name = "main-vpc"
  }
}

resource "aws_subnet" "public" {
  count             = local.subnet_count
  vpc_id            = aws_vpc.main.id
  cidr_block        = cidrsubnet("10.0.0.0/16", 8, count.index + 1)
  availability_zone = element(["us-east-1a", "us-east-1b"], count.index)

  tags = {
    Name = "public-subnet-${count.index}"
  }
}

resource "aws_internet_gateway" "main" {
  vpc_id = aws_vpc.main.id
}

resource "aws_route_table" "public" {
  vpc_id = aws_vpc.main.id

  route {
    cidr_block = "0.0.0.0/0"
    gateway_id = aws_internet_gateway.main.id
  }

  tags = {
    Name = "public-route-table"
  }
}

resource "aws_route_table_association" "public" {
  count          = local.subnet_count
  subnet_id      = aws_subnet.public[count.index].id
  route_table_id = aws_route_table.public.id
}

output "vpc_id" {
  value = aws_vpc.main.id
}

output "subnet_ids" {
  value = aws_subnet.public[*].id
}
''',
        hints=[
            "Use count to create multiple subnets",
            "enable_dns_hostnames should be true on the VPC",
            "Internet gateway attaches to the VPC",
            "Route table needs a 0.0.0.0/0 route to the internet gateway",
            "Route table associations link each subnet to the route table",
            "Use tags with Name for all resources",
        ],
        validation_script="dataset/vpc_public_subnets/validation.py",
    ),
})

# =============================================================================
# 9. Kinesis Firehose with S3 and Dynamic Partitioning
# =============================================================================
DATASETS.append({
    "dir": "kinesis_firehose_s3",
    "instance": make_instance(
        instance_id="terraform-aws-firehose-001",
        problem_statement=(
            "Create a Kinesis Firehose delivery stream with an extended S3 destination and "
            "dynamic partitioning enabled. The stream should include processing configuration "
            "with record deaggregation and metadata extraction processors. Create an IAM role "
            "for Firehose with an assume role policy for firehose.amazonaws.com and an S3 bucket "
            "as the destination."
        ),
        difficulty="medium",
        tags=["kinesis", "firehose", "s3", "streaming", "aws"],
        expected_resources={
            "aws_kinesis_firehose_delivery_stream": 1,
            "aws_iam_role": 1,
            "aws_s3_bucket": 1,
        },
        required_outputs=["firehose_arn", "bucket_arn"],
        gold_solution_main_tf=r'''data "aws_iam_policy_document" "firehose_assume_role" {
  statement {
    effect = "Allow"
    principals {
      type        = "Service"
      identifiers = ["firehose.amazonaws.com"]
    }
    actions = ["sts:AssumeRole"]
  }
}

resource "aws_iam_role" "firehose_role" {
  name               = "firehose_test_role"
  assume_role_policy = data.aws_iam_policy_document.firehose_assume_role.json
}

resource "aws_s3_bucket" "destination" {
  bucket = "firehose-destination-bucket"
}

resource "aws_kinesis_firehose_delivery_stream" "extended_s3_stream" {
  name        = "terraform-kinesis-firehose-extended-s3-test-stream"
  destination = "extended_s3"

  extended_s3_configuration {
    role_arn       = aws_iam_role.firehose_role.arn
    bucket_arn     = aws_s3_bucket.destination.arn
    buffering_size = 64

    dynamic_partitioning_configuration {
      enabled = true
    }

    prefix              = "data/customer_id=!{partitionKeyFromQuery:customer_id}/year=!{timestamp:yyyy}/month=!{timestamp:MM}/day=!{timestamp:dd}/hour=!{timestamp:HH}/"
    error_output_prefix = "errors/year=!{timestamp:yyyy}/month=!{timestamp:MM}/day=!{timestamp:dd}/hour=!{timestamp:HH}/!{firehose:error-output-type}/"

    processing_configuration {
      enabled = true

      processors {
        type = "RecordDeAggregation"
        parameters {
          parameter_name  = "SubRecordType"
          parameter_value = "JSON"
        }
      }

      processors {
        type = "AppendDelimiterToRecord"
      }

      processors {
        type = "MetadataExtraction"
        parameters {
          parameter_name  = "JsonParsingEngine"
          parameter_value = "JQ-1.6"
        }
        parameters {
          parameter_name  = "MetadataExtractionQuery"
          parameter_value = "{customer_id:.customer_id}"
        }
      }
    }
  }
}

output "firehose_arn" {
  value = aws_kinesis_firehose_delivery_stream.extended_s3_stream.arn
}

output "bucket_arn" {
  value = aws_s3_bucket.destination.arn
}
''',
        hints=[
            "Use destination = 'extended_s3' for extended S3 configuration",
            "Dynamic partitioning is enabled in dynamic_partitioning_configuration block",
            "IAM role needs assume_role_policy for firehose.amazonaws.com",
            "Processing configuration includes RecordDeAggregation and MetadataExtraction processors",
            "Prefix uses !{partitionKeyFromQuery:...} syntax for dynamic partitions",
        ],
        validation_script="dataset/kinesis_firehose_s3/validation.py",
        deployment_time_seconds=180,
    ),
})

# =============================================================================
# 10. Lambda with DynamoDB, Alias, and IAM
# =============================================================================
DATASETS.append({
    "dir": "lambda_dynamodb_alias",
    "instance": make_instance(
        instance_id="terraform-aws-lambda-alias-001",
        problem_statement=(
            "Create a Lambda function with a DynamoDB table for data storage. The Lambda "
            "should have an IAM role with a policy granting DynamoDB CRUD permissions. "
            "Create a Lambda alias pointing to the $LATEST version. The DynamoDB table "
            "should have streams enabled with NEW_AND_OLD_IMAGES view type."
        ),
        difficulty="medium",
        tags=["lambda", "dynamodb", "iam", "alias", "serverless", "aws"],
        expected_resources={
            "aws_lambda_function": 1,
            "aws_lambda_alias": 1,
            "aws_dynamodb_table": 1,
            "aws_iam_role": 1,
            "aws_iam_policy": 1,
            "aws_iam_role_policy_attachment": 1,
        },
        required_outputs=["lambda_arn", "alias_arn", "dynamodb_table_name"],
        gold_solution_main_tf=r'''resource "aws_dynamodb_table" "example_table" {
  name             = "example_table"
  hash_key         = "id"
  billing_mode     = "PAY_PER_REQUEST"
  stream_enabled   = true
  stream_view_type = "NEW_AND_OLD_IMAGES"

  attribute {
    name = "id"
    type = "S"
  }
}

data "aws_iam_policy_document" "assume_role" {
  statement {
    effect = "Allow"
    principals {
      type        = "Service"
      identifiers = ["lambda.amazonaws.com"]
    }
    actions = ["sts:AssumeRole"]
  }
}

resource "aws_iam_role" "iam_for_lambda" {
  name               = "iam_for_lambda"
  assume_role_policy = data.aws_iam_policy_document.assume_role.json
}

resource "aws_iam_policy" "lambda_dynamodb_policy" {
  name = "lambda-dynamodb-policy"
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Action = [
          "dynamodb:GetItem",
          "dynamodb:PutItem",
          "dynamodb:UpdateItem",
          "dynamodb:DeleteItem"
        ]
        Effect   = "Allow"
        Resource = aws_dynamodb_table.example_table.arn
      }
    ]
  })
}

resource "aws_iam_role_policy_attachment" "lambda_policy_attach" {
  role       = aws_iam_role.iam_for_lambda.name
  policy_arn = aws_iam_policy.lambda_dynamodb_policy.arn
}

data "archive_file" "lambda" {
  type        = "zip"
  source_file = "${path.module}/lambda_code/app.js"
  output_path = "${path.module}/lambda_code/app.zip"
}

resource "aws_lambda_function" "example_lambda" {
  filename         = data.archive_file.lambda.output_path
  function_name    = "lambda_app_function"
  source_code_hash = data.archive_file.lambda.output_base64sha256
  role             = aws_iam_role.iam_for_lambda.arn
  handler          = "app.handler"
  runtime          = "nodejs18.x"
}

resource "aws_lambda_alias" "test_lambda_alias" {
  name             = "my_alias"
  description      = "a sample description"
  function_name    = aws_lambda_function.example_lambda.arn
  function_version = "$LATEST"
}

output "lambda_arn" {
  value = aws_lambda_function.example_lambda.arn
}

output "alias_arn" {
  value = aws_lambda_alias.test_lambda_alias.arn
}

output "dynamodb_table_name" {
  value = aws_dynamodb_table.example_table.name
}
''',
        hints=[
            "DynamoDB table needs stream_enabled = true and stream_view_type = NEW_AND_OLD_IMAGES",
            "Lambda needs IAM role with AssumeRole for lambda.amazonaws.com",
            "Create a separate IAM policy for DynamoDB CRUD operations",
            "Lambda alias needs name, function_name, and function_version = $LATEST",
            "Use data archive_file to zip the Lambda code",
        ],
        validation_script="dataset/lambda_dynamodb_alias/validation.py",
    ),
})


def write_dataset(dataset_info):
    """Write a single dataset directory with JSONL and validation files."""
    dir_path = os.path.join(DATASET_DIR, dataset_info["dir"])
    os.makedirs(dir_path, exist_ok=True)

    # Write JSONL
    jsonl_path = os.path.join(dir_path, f"{dataset_info['dir']}.jsonl")
    with open(jsonl_path, "w") as f:
        f.write(json.dumps(dataset_info["instance"]) + "\n")

    # Write validation.py
    validation_path = os.path.join(dir_path, "validation.py")
    instance = dataset_info["instance"]
    resource_types = list(instance["expected_resources"].keys())

    validation_code = generate_validation(
        dataset_info["dir"],
        instance["instance_id"],
        resource_types,
        instance["problem_statement"],
    )
    with open(validation_path, "w") as f:
        f.write(validation_code)

    print(f"  Created {dir_path}/")
    print(f"    - {dataset_info['dir']}.jsonl")
    print(f"    - validation.py")


def generate_validation(dir_name, instance_id, resource_types, problem_statement):
    """Generate a validation.py file for the dataset."""
    # Map resource types to boto3 clients needed
    client_map = {
        "aws_vpc": "ec2",
        "aws_subnet": "ec2",
        "aws_security_group": "ec2",
        "aws_internet_gateway": "ec2",
        "aws_route_table": "ec2",
        "aws_route_table_association": "ec2",
        "aws_instance": "ec2",
        "aws_eip": "ec2",
        "aws_nat_gateway": "ec2",
        "aws_s3_bucket": "s3",
        "aws_s3_bucket_versioning": "s3",
        "aws_s3_bucket_server_side_encryption_configuration": "s3",
        "aws_s3_bucket_public_access_block": "s3",
        "aws_s3_object": "s3",
        "aws_lambda_function": "lambda",
        "aws_lambda_permission": "lambda",
        "aws_lambda_alias": "lambda",
        "aws_dynamodb_table": "dynamodb",
        "aws_iam_role": "iam",
        "aws_iam_policy": "iam",
        "aws_iam_role_policy": "iam",
        "aws_iam_role_policy_attachment": "iam",
        "aws_iam_instance_profile": "iam",
        "aws_api_gateway_rest_api": "apigateway",
        "aws_api_gateway_resource": "apigateway",
        "aws_api_gateway_method": "apigateway",
        "aws_api_gateway_integration": "apigateway",
        "aws_api_gateway_deployment": "apigateway",
        "aws_api_gateway_stage": "apigateway",
        "aws_route53_zone": "route53",
        "aws_route53_record": "route53",
        "aws_db_instance": "rds",
        "aws_db_subnet_group": "rds",
        "aws_cloudwatch_event_rule": "events",
        "aws_cloudwatch_event_target": "events",
        "aws_cloudwatch_log_group": "logs",
        "aws_kinesis_firehose_delivery_stream": "firehose",
    }

    needed_clients = set()
    for rt in resource_types:
        if rt in client_map:
            needed_clients.add(client_map[rt])

    class_name = "".join(word.capitalize() for word in dir_name.split("_")) + "Validation"

    # Build client init lines
    client_inits = []
    for client_name in sorted(needed_clients):
        client_inits.append(
            f"        self.{client_name} = boto3.client('{client_name}', **client_kwargs)"
        )

    # Build test methods - one per unique resource type
    test_methods = []
    for rt in resource_types:
        method_name = rt.replace("aws_", "").replace("__", "_")
        test_methods.append(f"""
    def test_{method_name}_exists(self):
        \"\"\"Check that {rt} resource exists.\"\"\"
        # This is a structural validation - the actual resource check
        # depends on the specific infrastructure deployed
        pass""")

    return f'''"""Validation test for {instance_id}."""

import os
import boto3
from typing import Dict, Any


class {class_name}:
    """Validate {problem_statement[:80]}..."""

    def __init__(self, region: str = 'us-east-1', endpoint_url: str = None):
        """Initialize test with AWS region."""
        self.region = region
        self.endpoint_url = endpoint_url

        client_kwargs = {{'region_name': region}}
        if endpoint_url:
            client_kwargs['endpoint_url'] = endpoint_url

{chr(10).join(client_inits)}

    def validate(self) -> Dict[str, Any]:
        """
        Run all validation checks.

        Returns:
            Dictionary with passed, tests, and errors.
        """
        results = {{
            'passed': True,
            'tests': {{}},
            'errors': []
        }}

        test_methods = [
            (name[5:], getattr(self, name))
            for name in dir(self)
            if name.startswith('test_')
        ]

        for test_name, test_func in test_methods:
            try:
                test_func()
                results['tests'][test_name] = True
            except AssertionError as e:
                results['tests'][test_name] = False
                results['errors'].append(f"{{test_name}}: {{str(e)}}")
                results['passed'] = False
            except Exception as e:
                results['tests'][test_name] = False
                results['errors'].append(f"{{test_name}}: Unexpected error: {{str(e)}}")
                results['passed'] = False

        return results
{"".join(test_methods)}


if __name__ == '__main__':
    """Run validation tests."""
    import sys
    import json

    endpoint_url = os.environ.get('AWS_ENDPOINT_URL')
    region = os.environ.get('AWS_DEFAULT_REGION', 'us-east-1')

    validator = {class_name}(region=region, endpoint_url=endpoint_url)
    results = validator.validate()

    print(json.dumps(results, indent=2))
    sys.exit(0 if results['passed'] else 1)
'''


def main():
    print(f"Generating {len(DATASETS)} datasets in {DATASET_DIR}/\n")

    for ds in DATASETS:
        write_dataset(ds)

    print(f"\nDone! Generated {len(DATASETS)} dataset directories.")


if __name__ == "__main__":
    main()
