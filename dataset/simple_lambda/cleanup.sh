#!/bin/bash
set -e

echo "Starting cleanup for simple_lambda pre-existing infrastructure..."

BUCKET_NAME="lambda-code-bucket"

echo "Deleting S3 bucket contents and bucket: $BUCKET_NAME"

# Delete all objects in the bucket first
if [ -n "$AWS_ENDPOINT_URL" ]; then
    # LocalStack
    aws s3 rm "s3://$BUCKET_NAME" --recursive --endpoint-url "$AWS_ENDPOINT_URL" 2>/dev/null || echo "No objects to delete or bucket doesn't exist"
    aws s3api delete-bucket --bucket "$BUCKET_NAME" --endpoint-url "$AWS_ENDPOINT_URL" 2>/dev/null || echo "Bucket deletion failed or doesn't exist"
else
    # Real AWS
    aws s3 rm "s3://$BUCKET_NAME" --recursive 2>/dev/null || echo "No objects to delete or bucket doesn't exist"
    aws s3api delete-bucket --bucket "$BUCKET_NAME" 2>/dev/null || echo "Bucket deletion failed or doesn't exist"
fi

echo "Cleanup completed!"
