# Feature

We want to be allowed to have pre existing infrastructure (optional) in dataset, executed by an sh which dcan include:

1. Simple code (for lambdas for example)
2. Executions like: build go lambda, create a zip, create a lambda zip s3 bucket, upload it

The runner must execute this if exists, also refactor the lambda test at dataset/ lambda example to have go code, build it and create a bucket and upload it. also modify the promopt there if required to assume this bucket exists:
