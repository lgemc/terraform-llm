"""Tool-enabled agent for generating Terraform with documentation search."""

import json
import logging
from typing import Optional
from pathlib import Path

import litellm

from terraform_llm.tools.search import HybridSearch

logger = logging.getLogger(__name__)

# Global search index (loaded once per process)
_SEARCH_INDEX: Optional[HybridSearch] = None

# Tool definitions for the LLM
TERRAFORM_DOCS_TOOL = {
    "type": "function",
    "function": {
        "name": "search_terraform_docs",
        "description": "Search Terraform and provider documentation for syntax, resource types, and configuration examples. Use this to look up correct Terraform syntax, resource arguments, and best practices.",
        "parameters": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Search query for Terraform documentation (e.g., 'aws_s3_bucket versioning syntax', 'terraform aws provider configuration')",
                },
                "provider": {
                    "type": "string",
                    "description": "Cloud provider to search docs for (e.g., 'aws', 'google', 'azurerm'). Optional.",
                },
            },
            "required": ["query"],
        },
    },
}

SUBMIT_TERRAFORM_TOOL = {
    "type": "function",
    "function": {
        "name": "submit_terraform",
        "description": "Submit the final Terraform HCL configuration. Call this when you have generated valid Terraform code that solves the problem statement.",
        "parameters": {
            "type": "object",
            "properties": {
                "files": {
                    "type": "object",
                    "description": "Dictionary mapping filenames to HCL content. Use 'main.tf' for single-file configs, or multiple files like 'main.tf', 'variables.tf', 'outputs.tf' for organized configs.",
                    "additionalProperties": {
                        "type": "string"
                    },
                },
                "explanation": {
                    "type": "string",
                    "description": "Brief explanation of the Terraform configuration and any important decisions made.",
                },
            },
            "required": ["files"],
        },
    },
}

SYSTEM_PROMPT = """You are a Terraform expert assistant with access to documentation search tools.

Your task is to generate valid Terraform HCL configuration that solves the given problem statement.

You have access to these tools:
1. search_terraform_docs - Search Terraform and provider documentation for syntax and examples
2. submit_terraform - Submit your final Terraform configuration

Workflow:
1. Analyze the problem statement
2. If you need to verify syntax, check resource arguments, or find best practices, use search_terraform_docs
3. Once you have enough information, generate the complete Terraform configuration
4. Call submit_terraform with your final HCL code

Rules:
- Generate ONLY valid Terraform HCL code
- Include all necessary provider and resource blocks
- Use the specified provider and region
- You can use search_terraform_docs multiple times if needed
- Always call submit_terraform when done to provide your final answer
"""


def search_terraform_docs(query: str, provider: Optional[str] = None) -> str:
    """
    Search Terraform documentation using hybrid search index.

    Falls back to mock results if no index is loaded.

    Args:
        query: Search query
        provider: Optional cloud provider filter

    Returns:
        Search results as formatted string
    """
    global _SEARCH_INDEX

    logger.info(f"Searching Terraform docs: query='{query}', provider='{provider}'")

    # Use hybrid search if available
    if _SEARCH_INDEX is not None:
        try:
            results = _SEARCH_INDEX.search(query, top_k=3, provider_filter=provider)

            if not results:
                return "No documentation found for your query. Try rephrasing or being more specific."

            # Format results for LLM
            formatted_results = []
            for result in results:
                formatted_results.append(_SEARCH_INDEX.format_result_for_llm(result))

            return "\n\n---\n\n".join(formatted_results)
        except Exception as e:
            logger.error(f"Hybrid search failed: {e}", exc_info=True)
            return f"Search error: {e}. Proceeding without documentation."

    # Fallback: mock results (for backward compatibility when no index is provided)
    logger.warning("No search index loaded, using mock documentation results")
    return _get_mock_docs(query)


def _get_mock_docs(query: str) -> str:
    """Fallback mock documentation for when no index is available."""
    results = []
    query_lower = query.lower()

    if "s3" in query_lower and "bucket" in query_lower:
        results.append("""
Resource: aws_s3_bucket
- Use aws_s3_bucket for the main bucket resource
- Use aws_s3_bucket_versioning for versioning (separate resource in newer providers)
- Use aws_s3_bucket_public_access_block for access control
Example:
  resource "aws_s3_bucket" "example" {
    bucket = "my-bucket-name"
  }
""")

    if "versioning" in query_lower:
        results.append("""
S3 Versioning:
- In AWS Provider v4+, versioning is a separate resource
- Use aws_s3_bucket_versioning linked to bucket via bucket_id
Example:
  resource "aws_s3_bucket_versioning" "example" {
    bucket = aws_s3_bucket.example.id
    versioning_configuration {
      status = "Enabled"
    }
  }
""")

    if "provider" in query_lower or "configuration" in query_lower:
        results.append("""
Provider Configuration:
- Define provider block with region
- Example for AWS:
  provider "aws" {
    region = "us-east-1"
  }
- For LocalStack testing, set endpoint configuration
""")

    if not results:
        results.append("""
General Terraform Documentation:
- Resource names follow pattern: <provider>_<service>_<resource>
- Always define required provider configuration
- Use variable blocks for parameterization
- Follow HCL syntax: blocks with { } braces
- Check Terraform Registry for specific resource documentation: registry.terraform.io
""")

    return "\n---\n".join(results)


def generate_hcl_with_tools(
    model: str,
    problem_statement: str,
    provider: str,
    region: str,
    hints: Optional[list[str]] = None,
    temperature: float = 0.0,
    max_tokens: int = 16384,
    max_iterations: int = 5,
    docs_index_path: Optional[str] = None,
    reasoning_effort: Optional[str] = None,
) -> tuple[dict[str, str], list[dict]]:
    """
    Generate Terraform HCL using a tool-enabled agent.

    The agent can search documentation before generating the final code.

    Args:
        model: Model identifier for litellm
        problem_statement: Natural language description of infrastructure
        provider: Cloud provider (e.g., "aws")
        region: Target region (e.g., "us-east-1")
        hints: Optional hints to include in the prompt
        temperature: Model temperature
        max_tokens: Maximum tokens per completion
        max_iterations: Maximum tool-calling iterations
        docs_index_path: Path to hybrid search index directory (optional)
        reasoning_effort: Reasoning effort level: "low", "medium", "high" (optional)

    Returns:
        Tuple of (generated_files, tool_call_trace, prompt)
        - generated_files: Dictionary mapping filenames to HCL content
        - tool_call_trace: List of tool calls made during generation
        - prompt: The initial prompt sent to the LLM

    Raises:
        RuntimeError: If agent doesn't submit terraform after max iterations
    """
    global _SEARCH_INDEX

    # Track all tool calls for trace
    tool_call_trace = []

    # Load search index if provided
    if docs_index_path and _SEARCH_INDEX is None:
        logger.info(f"Loading hybrid search index from {docs_index_path}")
        try:
            _SEARCH_INDEX = HybridSearch(Path(docs_index_path))
            logger.info("Hybrid search index loaded successfully")
        except Exception as e:
            logger.warning(f"Failed to load search index: {e}. Proceeding with mock docs.")
            _SEARCH_INDEX = None

    logger.info(f"Starting tool-enabled agent with model {model}")

    # Build initial user message
    user_content = f"Provider: {provider}\nRegion: {region}\n\n{problem_statement}"
    if hints:
        user_content += "\n\nHints:\n" + "\n".join(f"- {h}" for h in hints)

    # Build full prompt for trace
    full_prompt = f"System: {SYSTEM_PROMPT}\n\nUser: {user_content}"

    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": user_content},
    ]

    tools = [TERRAFORM_DOCS_TOOL, SUBMIT_TERRAFORM_TOOL]

    # Agentic loop
    for iteration in range(max_iterations):
        logger.debug(f"Tool iteration {iteration + 1}/{max_iterations}")

        # Build completion kwargs
        completion_kwargs = {
            "model": model,
            "messages": messages,
            "tools": tools,
            "temperature": temperature,
            "max_tokens": max_tokens,
        }

        # Add reasoning effort for reasoning models
        if reasoning_effort:
            completion_kwargs["reasoning_effort"] = reasoning_effort
            if iteration == 0:  # Log only once
                logger.info(f"Using reasoning effort: {reasoning_effort}")

        # For Ollama models, try to enable function calling support
        if model.startswith("ollama/") or model.startswith("ollama_chat/"):
            completion_kwargs["supports_function_calling"] = True
            if iteration == 0:
                logger.info("Ollama model detected, enabling function calling support")

        response = litellm.completion(**completion_kwargs)

        assistant_message = response.choices[0].message
        messages.append({
            "role": "assistant",
            "content": assistant_message.content,
            "tool_calls": assistant_message.tool_calls,
        })

        # Check if model called any tools
        if not assistant_message.tool_calls:
            # No tool calls - the model might not support function calling
            # Try to extract Terraform code from the response content
            logger.warning("Model didn't call any tools - attempting to extract HCL from response")

            if assistant_message.content:
                # Try to parse HCL from the response
                from terraform_llm.agent.models import parse_hcl_response
                try:
                    extracted_files = parse_hcl_response(assistant_message.content)
                    if extracted_files:
                        logger.info(f"Extracted {len(extracted_files)} file(s) from model response")
                        return extracted_files, tool_call_trace, full_prompt
                except Exception as e:
                    logger.error(f"Failed to extract HCL: {e}")

            # If extraction failed, prompt model to use submit_terraform tool
            if iteration < max_iterations - 1:
                logger.info("Prompting model to use submit_terraform tool")
                messages.append({
                    "role": "user",
                    "content": "Please call the submit_terraform tool with your Terraform configuration.",
                })
                continue
            else:
                # Last iteration, give up
                raise RuntimeError(
                    "Model does not support function calling and failed to generate valid Terraform code. "
                    "Try using --agent-type simple or use a model with function calling support "
                    "(e.g., ollama_chat/llama3.1, anthropic/claude-sonnet-4-5-20250929)"
                )

        # Process tool calls
        tool_results = []
        submitted_terraform = None

        for tool_call in assistant_message.tool_calls:
            tool_name = tool_call.function.name
            try:
                tool_args = json.loads(tool_call.function.arguments)
            except json.JSONDecodeError as e:
                logger.error(f"Failed to parse tool arguments: {e}")
                tool_results.append({
                    "tool_call_id": tool_call.id,
                    "role": "tool",
                    "name": tool_name,
                    "content": f"Error: Invalid JSON arguments: {e}",
                })
                continue

            logger.info(f"Tool call: {tool_name}({json.dumps(tool_args, indent=2)})")

            if tool_name == "search_terraform_docs":
                query = tool_args.get("query", "")
                provider_filter = tool_args.get("provider")
                result = search_terraform_docs(query, provider_filter)

                # Record search in trace
                tool_call_trace.append({
                    "iteration": iteration + 1,
                    "tool": "search_terraform_docs",
                    "query": query,
                    "provider": provider_filter,
                    "result_preview": result[:500] + "..." if len(result) > 500 else result,
                })

                tool_results.append({
                    "tool_call_id": tool_call.id,
                    "role": "tool",
                    "name": tool_name,
                    "content": result,
                })

            elif tool_name == "submit_terraform":
                files = tool_args.get("files", {})
                explanation = tool_args.get("explanation", "")

                if not files:
                    tool_results.append({
                        "tool_call_id": tool_call.id,
                        "role": "tool",
                        "name": tool_name,
                        "content": "Error: No files provided. Please provide at least one .tf file.",
                    })
                else:
                    # Success! Store the terraform files
                    submitted_terraform = files
                    logger.info(f"Terraform submitted: {len(files)} file(s)")
                    if explanation:
                        logger.info(f"Explanation: {explanation}")

                    # Record submission in trace
                    tool_call_trace.append({
                        "iteration": iteration + 1,
                        "tool": "submit_terraform",
                        "files": list(files.keys()),
                        "explanation": explanation,
                    })

                    tool_results.append({
                        "tool_call_id": tool_call.id,
                        "role": "tool",
                        "name": tool_name,
                        "content": f"Successfully submitted {len(files)} file(s). Task complete.",
                    })
            else:
                tool_results.append({
                    "tool_call_id": tool_call.id,
                    "role": "tool",
                    "name": tool_name,
                    "content": f"Error: Unknown tool '{tool_name}'",
                })

        # Add tool results to conversation
        messages.extend(tool_results)

        # If terraform was submitted, we're done
        if submitted_terraform:
            logger.info("Tool-enabled agent completed successfully")
            return submitted_terraform, tool_call_trace, full_prompt

    # Max iterations reached without submission
    error_msg = f"Agent did not submit Terraform configuration after {max_iterations} iterations"
    logger.error(error_msg)
    raise RuntimeError(error_msg)
