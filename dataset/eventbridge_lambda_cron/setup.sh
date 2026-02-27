#!/bin/bash
set -e

echo "Creating dummy Lambda code for eventbridge_lambda_cron..."

WORK_DIR="${WORK_DIR:-/workspace}"
mkdir -p "$WORK_DIR/lambda_code"

cat > "$WORK_DIR/lambda_code/handler.py" << 'PYEOF'
def handler(event, context):
    return {"statusCode": 200, "body": "ok"}
PYEOF

echo "Setup completed: created lambda_code/handler.py"
