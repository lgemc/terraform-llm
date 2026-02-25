"""LLM abstraction using litellm."""

import re
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
    "- Use the specified provider and region\n"
    "- Do not include explanations outside of HCL comments\n"
    "- If multiple files are needed, separate them with: # --- filename: <name>.tf ---"
)


@dataclass
class ModelConfig:
    """Configuration for an LLM model."""
    model: str
    temperature: float = 0.0
    max_tokens: int = 4096

    def to_dict(self) -> dict:
        """Convert to dictionary."""
        return {
            "model": self.model,
            "temperature": self.temperature,
            "max_tokens": self.max_tokens,
        }


def generate_hcl(
    config: ModelConfig,
    problem_statement: str,
    provider: str,
    region: str,
    hints: Optional[list[str]] = None,
) -> dict[str, str]:
    """
    Generate Terraform HCL from a problem statement.

    Args:
        config: Model configuration
        problem_statement: Natural language description of the infrastructure
        provider: Cloud provider (e.g. "aws")
        region: Target region (e.g. "us-east-1")
        hints: Optional hints to include in the prompt

    Returns:
        Dictionary mapping filenames to HCL content
    """
    user_content = f"Provider: {provider}\nRegion: {region}\n\n{problem_statement}"
    if hints:
        user_content += "\n\nHints:\n" + "\n".join(f"- {h}" for h in hints)

    logger.info(f"Generating HCL with model {config.model}")
    response = litellm.completion(
        model=config.model,
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_content},
        ],
        temperature=config.temperature,
        max_tokens=config.max_tokens,
    )

    response_text = response.choices[0].message.content
    logger.debug(f"LLM response length: {len(response_text)} chars")
    return parse_hcl_response(response_text)


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
