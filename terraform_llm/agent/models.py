"""LLM abstraction using litellm."""

import re
import os
import logging
from typing import Optional
from dataclasses import dataclass

import litellm

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = (
    "You are a Terraform expert. Given a problem statement, generate valid "
    "Terraform HCL configuration that solves it.\n\n"
    "Rules:\n"
    "- Output ONLY valid Terraform HCL code\n"
    "- Include all necessary provider and resource blocks\n"
    "- Use the specified provider and region from the problem statement\n"
    "- Do not include explanations outside of HCL comments\n"
    "- If multiple files are needed, separate them with: # --- filename: <name>.tf ---\n\n"
    "IMPORTANT: For AWS provider, include these LocalStack/Moto compatibility settings:\n"
    "provider \"aws\" {\n"
    "  region                      = \"us-east-1\"  # Use the region specified in the problem statement\n"
    "  s3_use_path_style           = true\n"
    "  skip_credentials_validation = true\n"
    "  skip_requesting_account_id  = true\n"
    "  skip_metadata_api_check     = true\n"
    "  endpoints {\n"
    "    # Will be set via AWS_ENDPOINT_URL environment variable\n"
    "  }\n"
    "}"
)


@dataclass
class ModelConfig:
    """Configuration for an LLM model."""
    model: str
    temperature: float = 0.0
    max_tokens: int = 16384
    agent_type: str = "simple"  # "simple" or "tool-enabled"
    max_tool_iterations: int = 5  # Max iterations for tool-enabled agent
    docs_index_path: Optional[str] = None  # Path to hybrid search index for tool-enabled agent
    reasoning_effort: Optional[str] = None  # Reasoning effort: "low", "medium", "high" (for reasoning models)
    multiturn: bool = False  # Enable multiturn refinement with validation feedback
    max_multiturn_iterations: int = 3  # Maximum multiturn refinement iterations

    def to_dict(self) -> dict:
        """Convert to dictionary."""
        return {
            "model": self.model,
            "temperature": self.temperature,
            "max_tokens": self.max_tokens,
            "agent_type": self.agent_type,
            "max_tool_iterations": self.max_tool_iterations,
            "docs_index_path": self.docs_index_path,
            "reasoning_effort": self.reasoning_effort,
            "multiturn": self.multiturn,
            "max_multiturn_iterations": self.max_multiturn_iterations,
        }


def generate_hcl(
    config: ModelConfig,
    problem_statement: str,
    provider: str,
    region: str,
    hints: Optional[list[str]] = None,
    validation_feedback: Optional[str] = None,
    messages: Optional[list[dict]] = None,
) -> tuple[dict[str, str], str, list[dict]]:
    """
    Generate Terraform HCL from a problem statement.

    Args:
        config: Model configuration
        problem_statement: Natural language description of the infrastructure
        provider: Cloud provider (e.g. "aws")
        region: Target region (e.g. "us-east-1")
        hints: Optional hints to include in the prompt
        validation_feedback: Optional feedback from previous validation (for multiturn)
        messages: Optional message history (for multiturn)

    Returns:
        Tuple of (generated_files, prompt, messages)
        - generated_files: Dictionary mapping filenames to HCL content
        - prompt: The actual prompt sent to the LLM
        - messages: The message history (for multiturn continuation)
    """
    # Initialize or use provided messages
    if messages is None:
        user_content = f"Provider: {provider}\nRegion: {region}\n\n{problem_statement}"
        if hints:
            user_content += "\n\nHints:\n" + "\n".join(f"- {h}" for h in hints)

        messages = [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_content},
        ]
    elif validation_feedback:
        # Add validation feedback to existing messages for refinement
        messages = list(messages)  # Copy to avoid mutating input
        messages.append({
            "role": "user",
            "content": f"The previous Terraform configuration had issues. Please fix them:\n\n{validation_feedback}\n\nProvide an updated Terraform configuration that addresses these issues.",
        })

    # Build full prompt for trace
    full_prompt = "\n\n".join([f"{msg['role'].capitalize()}: {msg['content']}" for msg in messages])

    logger.info(f"Generating HCL with model {config.model} (multiturn: {config.multiturn})")

    # Build completion kwargs
    completion_kwargs = {
        "model": config.model,
        "messages": messages,
        "temperature": config.temperature,
        "max_tokens": config.max_tokens,
    }

    # Add custom api_base from environment if set (for vLLM/custom OpenAI-compatible endpoints)
    if os.getenv("OPENAI_API_BASE"):
        completion_kwargs["api_base"] = os.getenv("OPENAI_API_BASE")
        logger.info(f"Using custom API base: {os.getenv('OPENAI_API_BASE')}")

    # Add reasoning effort for reasoning models (DeepSeek R1, o1, Claude 3.7+, gpt-oss)
    if config.reasoning_effort:
        completion_kwargs["reasoning_effort"] = config.reasoning_effort
        logger.info(f"Using reasoning effort: {config.reasoning_effort}")

    response = litellm.completion(**completion_kwargs)

    response_text = response.choices[0].message.content
    logger.debug(f"LLM response length: {len(response_text)} chars")

    # Add assistant response to messages
    messages.append({
        "role": "assistant",
        "content": response_text,
    })

    return parse_hcl_response(response_text), full_prompt, messages


def parse_hcl_response(response_text: str) -> dict[str, str]:
    """
    Parse LLM response into filename->content mapping.

    Handles:
    1. Markdown fences (```hcl or ```terraform)
    2. Multi-file markers: # --- filename: <name>.tf ---
    3. Single file: everything goes to main.tf

    Args:
        response_text: Raw LLM output

    Returns:
        Dictionary mapping filenames to HCL content
    """
    text = _strip_markdown_fences(response_text)

    # Check for multi-file markers
    marker_pattern = r"^#\s*---\s*filename:\s*(\S+)\s*---\s*$"
    parts = re.split(marker_pattern, text, flags=re.MULTILINE)

    if len(parts) > 1:
        # parts[0] is content before first marker (usually empty)
        # parts[1] is first filename, parts[2] is first content, etc.
        files = {}
        preamble = parts[0].strip()
        if preamble:
            files["main.tf"] = preamble

        for i in range(1, len(parts), 2):
            filename = parts[i].strip()
            content = parts[i + 1].strip() if i + 1 < len(parts) else ""
            if content:
                files[filename] = content
        return files

    # Single file
    return {"main.tf": text.strip()}


def _strip_markdown_fences(text: str) -> str:
    """Strip markdown code fences from LLM output."""
    # Match ```hcl, ```terraform, or plain ``` blocks
    fence_pattern = r"```(?:hcl|terraform|tf)?\s*\n(.*?)```"
    matches = re.findall(fence_pattern, text, flags=re.DOTALL)
    if matches:
        return "\n\n".join(matches)
    return text
