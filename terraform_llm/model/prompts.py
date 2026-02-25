"""Prompt templates for Terraform code generation."""

from typing import Dict, List, Optional


SYSTEM_PROMPT = """You are an expert Terraform engineer. Your task is to generate correct, production-ready Terraform configuration files based on infrastructure requirements.

Key guidelines:
- Write idiomatic, well-structured Terraform code
- Follow AWS/cloud provider best practices
- Include proper resource dependencies
- Use appropriate variable definitions
- Define useful outputs
- Add comments for complex configurations
- Ensure security best practices (encryption, least privilege, etc.)
"""


def create_generation_prompt(
    problem_statement: str,
    provider: str,
    region: str,
    hints: Optional[List[str]] = None,
    required_outputs: Optional[List[str]] = None
) -> str:
    """
    Create a prompt for Terraform code generation.

    Args:
        problem_statement: Natural language description of infrastructure
        provider: Cloud provider (aws, azure, gcp)
        region: Default region
        hints: Optional hints for implementation
        required_outputs: Optional required output names

    Returns:
        Formatted prompt string
    """
    prompt = f"""Generate Terraform configuration for the following infrastructure requirement:

REQUIREMENT:
{problem_statement}

PROVIDER: {provider}
REGION: {region}
"""

    if hints:
        prompt += "\n\nHINTS:\n"
        for hint in hints:
            prompt += f"- {hint}\n"

    if required_outputs:
        prompt += "\n\nREQUIRED OUTPUTS:\n"
        for output in required_outputs:
            prompt += f"- {output}\n"

    prompt += """

Please provide complete Terraform configuration files in the following format:

```main.tf
# Your main Terraform configuration here
```

```variables.tf
# Variable definitions (if needed)
```

```outputs.tf
# Output definitions (if needed)
```

Ensure the code is production-ready, follows best practices, and is properly formatted.
"""

    return prompt


def create_fix_prompt(
    original_code: str,
    error_message: str,
    problem_statement: str
) -> str:
    """
    Create a prompt to fix broken Terraform code.

    Args:
        original_code: The Terraform code that failed
        error_message: Error message from Terraform
        problem_statement: Original requirement

    Returns:
        Formatted prompt string
    """
    prompt = f"""The following Terraform code has errors. Please fix them.

ORIGINAL REQUIREMENT:
{problem_statement}

CURRENT CODE:
{original_code}

ERROR MESSAGE:
{error_message}

Please provide the corrected Terraform configuration files. Only show the files that need changes.
"""

    return prompt


def parse_terraform_response(response: str) -> Dict[str, str]:
    """
    Parse Terraform code from model response.

    Extracts code blocks for main.tf, variables.tf, outputs.tf, etc.

    Args:
        response: Raw model response

    Returns:
        Dictionary mapping filenames to contents
    """
    import re

    files = {}

    # Pattern to match code blocks with filenames
    # Matches: ```filename.tf or ```hcl followed by # filename.tf
    pattern = r'```(?:hcl\n)?(?:#\s*)?(\w+\.tf[vars]*)\n(.*?)```'

    matches = re.findall(pattern, response, re.DOTALL)

    for filename, content in matches:
        files[filename] = content.strip()

    # If no explicit filenames, look for generic terraform blocks
    if not files:
        # Try to find any HCL/terraform code block
        generic_pattern = r'```(?:hcl|terraform)\n(.*?)```'
        generic_matches = re.findall(generic_pattern, response, re.DOTALL)

        if generic_matches:
            # Assume first block is main.tf
            files['main.tf'] = generic_matches[0].strip()

            if len(generic_matches) > 1:
                files['outputs.tf'] = generic_matches[1].strip()

            if len(generic_matches) > 2:
                files['variables.tf'] = generic_matches[2].strip()

    return files


def create_multi_turn_messages(
    problem_statement: str,
    provider: str,
    region: str,
    hints: Optional[List[str]] = None,
    required_outputs: Optional[List[str]] = None,
    previous_attempts: Optional[List[Dict[str, str]]] = None
) -> List[Dict[str, str]]:
    """
    Create multi-turn conversation messages for iterative code generation.

    Args:
        problem_statement: Infrastructure requirement
        provider: Cloud provider
        region: Default region
        hints: Optional hints
        required_outputs: Required outputs
        previous_attempts: List of previous attempts with errors

    Returns:
        List of message dictionaries
    """
    messages = [
        {
            "role": "user",
            "content": create_generation_prompt(
                problem_statement,
                provider,
                region,
                hints,
                required_outputs
            )
        }
    ]

    if previous_attempts:
        for attempt in previous_attempts:
            # Add assistant's previous response
            if 'response' in attempt:
                messages.append({
                    "role": "assistant",
                    "content": attempt['response']
                })

            # Add user feedback about errors
            if 'error' in attempt:
                messages.append({
                    "role": "user",
                    "content": f"The code has the following error:\n\n{attempt['error']}\n\nPlease fix it."
                })

    return messages
