# Pre-existing Infrastructure Setup Plan

## Overview
Add support for optional pre-existing infrastructure in datasets, executed via shell scripts. This allows datasets to have setup steps like building code, creating S3 buckets, and uploading artifacts before running Terraform.

## Requirements
- Datasets can optionally include a `setup.sh` script for pre-existing infrastructure
- The runner must execute this script if it exists before running Terraform
- Refactor the `simple_lambda` example to demonstrate this feature with a Go Lambda

## Implementation Plan

### 1. Extend Dataset Schema
**File:** `terraform_llm/datasets/schema.py`

- Add optional `setup_script` field to `BenchmarkInstance` dataclass
  - Type: `Optional[str]`
  - Path to shell script relative to dataset directory
- Update `from_dict()` and `to_dict()` methods to handle the new field
- Update `validate_instance()` to optionally validate setup_script field

**Rationale:** The schema needs to support referencing a setup script so the executor knows to run it.

### 2. Update Executor to Run Setup Scripts
**File:** `terraform_llm/runtime/executor.py`

- Add `_run_setup_script()` method to `BenchmarkExecutor` class
  - Execute the shell script in the instance directory
  - Capture stdout/stderr
  - Return success/failure status
  - Set appropriate environment variables (AWS region, endpoint URL for LocalStack, etc.)
- Modify `execute_instance()` method to:
  - Accept optional `setup_script` parameter
  - Run `_run_setup_script()` before `_create_terraform_files()` if setup_script is provided
  - Store setup results in results dictionary
  - Abort execution if setup fails

**Rationale:** The executor orchestrates the full workflow and needs to run setup before Terraform.

### 3. Create Go Lambda Example Code
**New directory:** `dataset/simple_lambda/lambda_code/`

- Create `main.go` with a simple Go Lambda handler:
  ```go
  package main

  import (
      "context"
      "github.com/aws/aws-lambda-go/lambda"
  )

  type Response struct {
      Message string `json:"message"`
  }

  func handler(ctx context.Context) (Response, error) {
      return Response{Message: "Hello from Go Lambda!"}, nil
  }

  func main() {
      lambda.Start(handler)
  }
  ```
- Create `go.mod` with required dependencies

**Rationale:** Provides actual Lambda code to build rather than assuming a pre-existing zip.

### 4. Create Setup Script for Lambda
**New file:** `dataset/simple_lambda/setup.sh`

The script should:
1. Build the Go Lambda:
   - `cd` to `lambda_code/` directory
   - Run `GOOS=linux GOARCH=amd64 go build -o bootstrap main.go`
   - Create `lambda.zip` containing the `bootstrap` binary
2. Create S3 bucket for Lambda deployment:
   - Use AWS CLI or boto3 to create bucket
   - Handle LocalStack vs real AWS based on environment variables
   - Bucket name: `lambda-code-bucket-${RANDOM_SUFFIX}` (or use fixed name for testing)
3. Upload `lambda.zip` to S3 bucket
4. Export environment variables for Terraform:
   - `LAMBDA_BUCKET_NAME`
   - `LAMBDA_OBJECT_KEY`

**Notes:**
- Make script idempotent (check if bucket exists before creating)
- Handle LocalStack endpoint URL via environment variable
- Proper error handling with exit codes

### 5. Update Lambda Terraform Code
**File:** `dataset/simple_lambda/simple_lambda.jsonl`

Update the `gold_solution` to:
- Reference S3 bucket and object key via variables or environment
- Use `aws_s3_bucket` data source (not resource) to reference pre-existing bucket
- Update `aws_lambda_function` to use:
  ```hcl
  s3_bucket = data.aws_s3_bucket.lambda_code.bucket
  s3_key    = "lambda.zip"
  ```
- Change runtime from `python3.9` to `go1.x` (or `provided.al2` for custom runtime)
- Update handler to `bootstrap` (Go Lambda convention)

**Rationale:** Terraform should assume the S3 bucket with Lambda code already exists from the setup script.

### 6. Update Lambda Problem Statement
**File:** `dataset/simple_lambda/simple_lambda.jsonl`

Update `problem_statement` to:
- Mention that Lambda code already exists in S3 bucket `lambda-code-bucket`
- Specify to use Go runtime instead of Python
- Reference the existing S3 bucket in the solution

Example:
```
Create an AWS Lambda function named 'hello_world' using the Go runtime.
The Lambda code already exists in S3 bucket 'lambda-code-bucket' with key 'lambda.zip'.
The function should have basic execution role with CloudWatch Logs permissions.
```

### 7. Update Lambda Validation Script
**File:** `dataset/simple_lambda/validation.py`

- Update `test_lambda_runtime()` to check for `go1.x` or `provided.al2` runtime instead of `python3.9`
- Add test to verify Lambda uses S3 deployment (not local file)
- Optionally add test to invoke the Lambda and verify response

### 8. Update Dataset Loader
**File:** `terraform_llm/datasets/loader.py` (if needed)

- Ensure loader properly handles the new `setup_script` field when loading datasets
- Resolve setup_script path relative to dataset directory

### 9. Add Cleanup for Pre-existing Infrastructure
**File:** `terraform_llm/runtime/executor.py`

- Add optional `_run_cleanup_script()` method or extend `_cleanup()` to:
  - Delete S3 bucket and contents created by setup script
  - Clean up any other pre-existing infrastructure
- Consider adding optional `cleanup.sh` script support in datasets

**Rationale:** Pre-existing infrastructure should also be cleaned up after tests.

## Testing Checklist

- [ ] Schema validation accepts setup_script field
- [ ] Executor runs setup script before Terraform
- [ ] Setup script builds Go Lambda successfully
- [ ] Setup script creates S3 bucket and uploads zip
- [ ] Terraform can reference pre-existing S3 bucket
- [ ] Validation tests pass with Go Lambda
- [ ] Cleanup removes both Terraform resources and setup resources
- [ ] Works with LocalStack (using AWS_ENDPOINT_URL)
- [ ] Works with real AWS
- [ ] Simple VPC example still works (no setup script)

## File Summary

**New Files:**
- `dataset/simple_lambda/lambda_code/main.go`
- `dataset/simple_lambda/lambda_code/go.mod`
- `dataset/simple_lambda/setup.sh`

**Modified Files:**
- `terraform_llm/datasets/schema.py`
- `terraform_llm/runtime/executor.py`
- `dataset/simple_lambda/simple_lambda.jsonl`
- `dataset/simple_lambda/validation.py`
- `terraform_llm/datasets/loader.py` (possibly)

## Notes

- Setup scripts should be bash-compatible and portable
- Environment variables for LocalStack: `AWS_ENDPOINT_URL`, `AWS_DEFAULT_REGION`
- Consider adding setup script timeout to prevent hanging
- Setup script output should be logged for debugging
- Future: Could extend to support setup scripts in other languages (Python, etc.)
