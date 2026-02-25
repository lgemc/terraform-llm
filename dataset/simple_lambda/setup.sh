#!/bin/bash
set -e

echo "Starting setup for simple_lambda..."

# Get the directory where the script is located
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
LAMBDA_CODE_DIR="$SCRIPT_DIR/lambda_code"

# Build the Go Lambda
echo "Building Go Lambda..."
cd "$LAMBDA_CODE_DIR"

# Initialize Go module and download dependencies
go mod tidy

# Build for Lambda (Linux AMD64)
GOOS=linux GOARCH=amd64 go build -o bootstrap main.go

# Create deployment package
echo "Creating deployment package..."
zip lambda.zip bootstrap

# Set bucket name (using a fixed name for testing with LocalStack)
BUCKET_NAME="lambda-code-bucket"
OBJECT_KEY="lambda.zip"

# Create S3 bucket
echo "Creating S3 bucket: $BUCKET_NAME"
if [ -n "$AWS_ENDPOINT_URL" ]; then
    # LocalStack
    aws s3api create-bucket \
        --bucket "$BUCKET_NAME" \
        --endpoint-url "$AWS_ENDPOINT_URL" \
        --region "${AWS_DEFAULT_REGION:-us-east-1}" \
        2>/dev/null || echo "Bucket already exists or creation failed, continuing..."
else
    # Real AWS
    if [ "${AWS_DEFAULT_REGION}" = "us-east-1" ]; then
        aws s3api create-bucket \
            --bucket "$BUCKET_NAME" \
            --region "${AWS_DEFAULT_REGION:-us-east-1}" \
            2>/dev/null || echo "Bucket already exists or creation failed, continuing..."
    else
        aws s3api create-bucket \
            --bucket "$BUCKET_NAME" \
            --region "${AWS_DEFAULT_REGION:-us-east-1}" \
            --create-bucket-configuration LocationConstraint="${AWS_DEFAULT_REGION}" \
            2>/dev/null || echo "Bucket already exists or creation failed, continuing..."
    fi
fi

# Upload Lambda code to S3
echo "Uploading Lambda code to S3..."
if [ -n "$AWS_ENDPOINT_URL" ]; then
    aws s3 cp lambda.zip "s3://$BUCKET_NAME/$OBJECT_KEY" \
        --endpoint-url "$AWS_ENDPOINT_URL"
else
    aws s3 cp lambda.zip "s3://$BUCKET_NAME/$OBJECT_KEY"
fi

# Export environment variables for Terraform
export LAMBDA_BUCKET_NAME="$BUCKET_NAME"
export LAMBDA_OBJECT_KEY="$OBJECT_KEY"

echo "Setup completed successfully!"
echo "LAMBDA_BUCKET_NAME=$LAMBDA_BUCKET_NAME"
echo "LAMBDA_OBJECT_KEY=$LAMBDA_OBJECT_KEY"
