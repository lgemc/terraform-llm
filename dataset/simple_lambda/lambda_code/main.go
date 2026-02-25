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
