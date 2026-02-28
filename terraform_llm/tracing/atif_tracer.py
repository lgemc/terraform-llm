"""ATIF trajectory generator for terraform-agent."""

import uuid
from datetime import datetime
from typing import Dict, Any, List, Optional

from terraform_llm.tracing.atif import (
    Trajectory,
    AgentSchema,
    StepObject,
    ToolCallSchema,
    ObservationSchema,
    ObservationResultSchema,
    MetricsSchema,
    FinalMetricsSchema,
    ToolDefinition,
)


class ATIFTracer:
    """Generate ATIF-compliant trajectories from terraform-agent execution."""

    def __init__(self, agent_version: str = "1.0.0"):
        """
        Initialize ATIF tracer.

        Args:
            agent_version: Version of terraform-agent
        """
        self.agent_version = agent_version
        self.session_id = str(uuid.uuid4())
        self.steps: List[StepObject] = []
        self.tool_definitions: List[ToolDefinition] = []
        self.model_name: Optional[str] = None
        self.agent_type: Optional[str] = None
        self.total_prompt_tokens = 0
        self.total_completion_tokens = 0
        self.total_cost_usd = 0.0

    def set_model(self, model_name: str, agent_type: str = "simple") -> None:
        """Set the model and agent type for this trajectory."""
        self.model_name = model_name
        self.agent_type = agent_type

    def add_tool_definitions(self, tool_defs: List[Dict[str, Any]]) -> None:
        """
        Add tool definitions to the trajectory.

        Args:
            tool_defs: List of tool definition dicts (OpenAI format)
        """
        for tool_def in tool_defs:
            self.tool_definitions.append(
                ToolDefinition(
                    type=tool_def.get("type", "function"),
                    function=tool_def.get("function", {})
                )
            )

    def add_user_message(self, message: str) -> None:
        """
        Add a user message step.

        Args:
            message: User's message content
        """
        step = StepObject(
            step_id=len(self.steps) + 1,
            timestamp=datetime.utcnow().isoformat() + "Z",
            source="user",
            message=message,
        )
        self.steps.append(step)

    def add_agent_step(
        self,
        message: str,
        reasoning_content: Optional[str] = None,
        tool_calls: Optional[List[Dict[str, Any]]] = None,
        observation: Optional[Dict[str, Any]] = None,
        metrics: Optional[Dict[str, Any]] = None,
        model_name: Optional[str] = None,
    ) -> None:
        """
        Add an agent step with optional tool calls and observations.

        Args:
            message: Agent's response message
            reasoning_content: Agent's internal reasoning
            tool_calls: List of tool calls made
            observation: Observation/results from tool execution
            metrics: LLM metrics (tokens, cost, etc.)
            model_name: Override model for this step
        """
        # Convert tool calls to ATIF format
        atif_tool_calls = None
        if tool_calls:
            atif_tool_calls = [
                ToolCallSchema(
                    tool_call_id=tc.get("tool_call_id", f"call_{i}"),
                    function_name=tc.get("function_name", tc.get("name", "")),
                    arguments=tc.get("arguments", {}),
                )
                for i, tc in enumerate(tool_calls)
            ]

        # Convert observation to ATIF format
        atif_observation = None
        if observation:
            results = []
            if isinstance(observation, dict) and "results" in observation:
                for result in observation["results"]:
                    results.append(
                        ObservationResultSchema(
                            source_call_id=result.get("source_call_id"),
                            content=result.get("content"),
                        )
                    )
            else:
                # Single observation result
                results.append(
                    ObservationResultSchema(
                        content=str(observation)
                    )
                )
            atif_observation = ObservationSchema(results=results)

        # Convert metrics to ATIF format
        atif_metrics = None
        if metrics:
            atif_metrics = MetricsSchema(
                prompt_tokens=metrics.get("prompt_tokens"),
                completion_tokens=metrics.get("completion_tokens"),
                cached_tokens=metrics.get("cached_tokens"),
                cost_usd=metrics.get("cost_usd"),
                extra=metrics.get("extra"),
            )
            # Track totals
            self.total_prompt_tokens += metrics.get("prompt_tokens", 0)
            self.total_completion_tokens += metrics.get("completion_tokens", 0)
            self.total_cost_usd += metrics.get("cost_usd", 0.0)

        step = StepObject(
            step_id=len(self.steps) + 1,
            timestamp=datetime.utcnow().isoformat() + "Z",
            source="agent",
            model_name=model_name or self.model_name,
            message=message,
            reasoning_content=reasoning_content,
            tool_calls=atif_tool_calls,
            observation=atif_observation,
            metrics=atif_metrics,
        )
        self.steps.append(step)

    def from_terraform_trajectory(
        self,
        instance_id: str,
        problem_statement: str,
        model: str,
        agent_type: str,
        generated_files: Dict[str, str],
        stages: List[Dict[str, Any]],
        tool_calls: Optional[List[Dict[str, Any]]] = None,
        prompt: Optional[str] = None,
    ) -> Trajectory:
        """
        Convert a terraform-agent trajectory to ATIF format.

        Args:
            instance_id: Instance identifier
            problem_statement: Problem description
            model: Model name used
            agent_type: Type of agent (simple, tool-enabled)
            generated_files: Generated Terraform files
            stages: Execution stages (init, validate, plan, etc.)
            tool_calls: Optional tool call trace
            prompt: Optional full prompt sent to LLM

        Returns:
            ATIF Trajectory object
        """
        self.set_model(model, agent_type)
        self.session_id = instance_id  # Use instance_id as session_id for consistency
        self.steps = []

        # Step 1: User provides problem statement
        self.add_user_message(problem_statement)

        # Step 2: Agent generation phase
        if agent_type == "tool-enabled" and tool_calls:
            # Tool-enabled agent: Add tool calls and observations
            for i, tc in enumerate(tool_calls):
                # Add agent step with tool call
                tool_name = tc.get("name", tc.get("function_name", "unknown"))
                tool_args = tc.get("arguments", {})
                result = tc.get("result", "")

                # Create tool call
                atif_tc = [{
                    "tool_call_id": f"call_{i}",
                    "function_name": tool_name,
                    "arguments": tool_args,
                }]

                # Create observation
                obs = {
                    "results": [{
                        "source_call_id": f"call_{i}",
                        "content": result,
                    }]
                }

                # Add step
                self.add_agent_step(
                    message=f"Calling {tool_name}",
                    tool_calls=atif_tc,
                    observation=obs,
                )

        # Final agent step: Submit generated code
        files_summary = "\n\n".join([
            f"### {filename}\n```hcl\n{content}\n```"
            for filename, content in generated_files.items()
        ])

        self.add_agent_step(
            message=f"Generated {len(generated_files)} Terraform file(s):\n\n{files_summary}",
            reasoning_content=prompt if prompt else None,
        )

        # Step 3+: Execution stages as system steps with observations
        for stage_dict in stages:
            stage_name = stage_dict.get("stage", "unknown")
            status = stage_dict.get("status", "unknown")
            output = stage_dict.get("output", "")
            message_text = stage_dict.get("message", "")
            details = stage_dict.get("details", {})
            duration = stage_dict.get("duration_seconds", 0.0)

            # Determine content for observation
            if output:
                content = output
            elif details:
                content = str(details)
            else:
                content = f"Status: {status}"

            # Create system step for stage execution
            step = StepObject(
                step_id=len(self.steps) + 1,
                timestamp=datetime.utcnow().isoformat() + "Z",
                source="system",
                message=f"Terraform {stage_name}: {message_text}",
                observation=ObservationSchema(
                    results=[
                        ObservationResultSchema(
                            content=content
                        )
                    ]
                ),
                extra={
                    "stage": stage_name,
                    "status": status,
                    "score": stage_dict.get("score", 0.0),
                    "duration_seconds": duration,
                    "details": details if details else None,
                    "message": message_text,
                },
            )
            self.steps.append(step)

        # Build final trajectory
        agent = AgentSchema(
            name="terraform-agent",
            version=self.agent_version,
            model_name=model,
            tool_definitions=self.tool_definitions if self.tool_definitions else None,
            extra={"agent_type": agent_type},
        )

        final_metrics = FinalMetricsSchema(
            total_prompt_tokens=self.total_prompt_tokens if self.total_prompt_tokens > 0 else None,
            total_completion_tokens=self.total_completion_tokens if self.total_completion_tokens > 0 else None,
            total_cost_usd=self.total_cost_usd if self.total_cost_usd > 0 else None,
            total_steps=len(self.steps),
            extra={"instance_id": instance_id},
        )

        trajectory = Trajectory(
            session_id=self.session_id,
            agent=agent,
            steps=self.steps,
            final_metrics=final_metrics,
            extra={
                "instance_id": instance_id,
                "problem_statement": problem_statement,
                "generated_files": generated_files,
            },
        )

        return trajectory

    def to_trajectory(
        self,
        notes: Optional[str] = None,
        extra: Optional[Dict[str, Any]] = None,
    ) -> Trajectory:
        """
        Build final ATIF trajectory.

        Args:
            notes: Optional notes about the trajectory
            extra: Optional extra metadata

        Returns:
            ATIF Trajectory object
        """
        agent = AgentSchema(
            name="terraform-agent",
            version=self.agent_version,
            model_name=self.model_name,
            tool_definitions=self.tool_definitions if self.tool_definitions else None,
            extra={"agent_type": self.agent_type} if self.agent_type else None,
        )

        final_metrics = FinalMetricsSchema(
            total_prompt_tokens=self.total_prompt_tokens if self.total_prompt_tokens > 0 else None,
            total_completion_tokens=self.total_completion_tokens if self.total_completion_tokens > 0 else None,
            total_cost_usd=self.total_cost_usd if self.total_cost_usd > 0 else None,
            total_steps=len(self.steps),
        )

        trajectory = Trajectory(
            session_id=self.session_id,
            agent=agent,
            steps=self.steps,
            notes=notes,
            final_metrics=final_metrics,
            extra=extra,
        )

        return trajectory
