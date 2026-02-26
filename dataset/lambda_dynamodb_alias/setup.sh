#!/bin/bash
set -e

echo "Creating dummy Lambda code for lambda_dynamodb_alias..."

WORK_DIR="${WORK_DIR:-/workspace}"
mkdir -p "$WORK_DIR/lambda_code"

cat > "$WORK_DIR/lambda_code/app.js" << 'JSEOF'
exports.handler = async (event) => {
    return { statusCode: 200, body: "ok" };
};
JSEOF

echo "Setup completed: created lambda_code/app.js"
