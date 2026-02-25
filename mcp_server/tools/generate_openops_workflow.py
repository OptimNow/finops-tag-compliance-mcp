# Copyright (c) 2025-2026 OptimNow. All Rights Reserved.
# Licensed under the Apache License, Version 2.0.
# See LICENSE file in the project root for full license information.

"""MCP tool for generating OpenOps automation workflows from compliance violations."""

import logging
from datetime import datetime
from typing import Any

import yaml
from pydantic import BaseModel, Field

from ..services.compliance_service import ComplianceService
from ..services.policy_service import PolicyService

logger = logging.getLogger(__name__)


class WorkflowStep(BaseModel):
    """A single step in an OpenOps workflow."""

    name: str = Field(..., description="Step name")
    action: str = Field(..., description="Action type (e.g., 'aws_cli', 'notification')")
    description: str = Field("", description="Human-readable step description")


class GenerateOpenOpsWorkflowResult(BaseModel):
    """Result from the generate_openops_workflow tool."""

    workflow_name: str = Field(..., description="Name of the generated workflow")
    yaml_content: str = Field(..., description="Complete YAML workflow content")
    description: str = Field(..., description="Workflow description")
    steps: list[WorkflowStep] = Field(
        default_factory=list, description="Workflow steps summary"
    )
    step_count: int = Field(0, description="Number of steps in the workflow")
    resource_types: list[str] = Field(
        default_factory=list, description="Resource types targeted"
    )
    remediation_strategy: str = Field(
        ..., description="Strategy used: 'auto_tag', 'notify', or 'report'"
    )

    def model_post_init(self, __context) -> None:
        """Compute step_count after initialization."""
        object.__setattr__(self, "step_count", len(self.steps))


async def generate_openops_workflow(
    policy_service: PolicyService,
    resource_types: list[str],
    remediation_strategy: str = "notify",
    threshold: float = 0.8,
    target_tags: list[str] | None = None,
    schedule: str | None = None,
    compliance_service: ComplianceService | None = None,
) -> GenerateOpenOpsWorkflowResult:
    """
    Generate an OpenOps-compatible automation workflow from compliance violations.

    Creates YAML workflows that can be imported into OpenOps or similar
    automation platforms to remediate tag compliance violations.

    Args:
        policy_service: PolicyService for retrieving tagging policy configuration
        resource_types: List of resource types to target
            (e.g., ["ec2:instance", "rds:db"])
        remediation_strategy: How to remediate violations:
            - "auto_tag": Automatically apply default tag values
            - "notify": Send notifications about violations
            - "report": Generate a compliance report
            Default: "notify"
        threshold: Compliance score threshold (0.0-1.0) that triggers the workflow.
            Default: 0.8 (trigger when compliance drops below 80%)
        target_tags: Specific tags to include in remediation.
            If None, uses all required tags from policy.
        schedule: Optional cron schedule for recurring execution
            (e.g., "0 9 * * MON" for every Monday at 9 AM)
        compliance_service: Optional ComplianceService (reserved for future use)

    Returns:
        GenerateOpenOpsWorkflowResult containing:
        - workflow_name: Name of the generated workflow
        - yaml_content: Complete YAML workflow
        - description: Workflow description
        - steps: Summary of workflow steps
        - step_count: Number of steps
        - resource_types: Targeted resource types
        - remediation_strategy: Strategy used

    Raises:
        ValueError: If resource_types is empty or remediation_strategy is invalid

    Example:
        >>> result = await generate_openops_workflow(
        ...     policy_service=policy,
        ...     resource_types=["ec2:instance"],
        ...     remediation_strategy="notify",
        ...     threshold=0.8,
        ... )
        >>> print(result.yaml_content)
    """
    if not resource_types:
        raise ValueError("resource_types cannot be empty")

    valid_strategies = {"auto_tag", "notify", "report"}
    if remediation_strategy not in valid_strategies:
        raise ValueError(
            f"Invalid remediation_strategy '{remediation_strategy}'. "
            f"Must be one of: {valid_strategies}"
        )

    if threshold < 0.0 or threshold > 1.0:
        raise ValueError("threshold must be between 0.0 and 1.0")

    logger.info(
        f"Generating OpenOps workflow for resource_types={resource_types}, "
        f"strategy={remediation_strategy}, threshold={threshold}"
    )

    # Get the tagging policy
    policy = policy_service.get_policy()

    # Determine which tags to target
    if target_tags:
        tags_to_target = [
            tag for tag in policy.required_tags if tag.name in target_tags
        ]
    else:
        tags_to_target = policy.required_tags
        target_tags = [t.name for t in tags_to_target]

    # Build workflow
    resource_types_display = ", ".join(resource_types)
    workflow_name = f"Fix {resource_types_display} Tagging Violations"

    workflow = _build_openops_workflow(
        workflow_name=workflow_name,
        resource_types=resource_types,
        tags=tags_to_target,
        target_tag_names=target_tags,
        remediation_strategy=remediation_strategy,
        threshold=threshold,
        schedule=schedule,
    )

    yaml_content = yaml.dump(workflow, default_flow_style=False, sort_keys=False)

    # Extract step summaries
    steps = []
    for step_data in workflow.get("steps", []):
        steps.append(
            WorkflowStep(
                name=step_data.get("name", ""),
                action=step_data.get("action", ""),
                description=step_data.get("description", ""),
            )
        )

    description = (
        f"Workflow to {remediation_strategy} tagging violations for "
        f"{resource_types_display}. Triggers when compliance score drops below "
        f"{threshold:.0%}."
    )

    logger.info(f"Generated OpenOps workflow with {len(steps)} steps")

    return GenerateOpenOpsWorkflowResult(
        workflow_name=workflow_name,
        yaml_content=yaml_content,
        description=description,
        steps=steps,
        resource_types=resource_types,
        remediation_strategy=remediation_strategy,
    )


def _build_openops_workflow(
    workflow_name: str,
    resource_types: list[str],
    tags: list,
    target_tag_names: list[str],
    remediation_strategy: str,
    threshold: float,
    schedule: str | None,
) -> dict[str, Any]:
    """Build the OpenOps workflow dict.

    Args:
        workflow_name: Name for the workflow
        resource_types: Resource types to target
        tags: RequiredTag objects from policy
        target_tag_names: Tag key names
        remediation_strategy: Strategy (auto_tag, notify, report)
        threshold: Compliance score threshold
        schedule: Optional cron schedule

    Returns:
        OpenOps workflow dict
    """
    workflow: dict[str, Any] = {
        "name": workflow_name,
        "version": "1.0",
        "description": (
            f"Automated remediation of tag compliance violations for "
            f"{', '.join(resource_types)}."
        ),
    }

    # Triggers
    triggers: list[dict[str, Any]] = [
        {"compliance_score_below": threshold},
    ]
    if schedule:
        triggers.append({"schedule": schedule})

    workflow["triggers"] = triggers

    # Filters
    workflow["filters"] = {
        "resource_types": resource_types,
        "tag_keys": target_tag_names,
    }

    # Steps based on remediation strategy
    steps: list[dict[str, Any]] = []

    if remediation_strategy == "auto_tag":
        # Step 1: Identify non-compliant resources
        steps.append(
            {
                "name": "Identify Non-Compliant Resources",
                "action": "compliance_check",
                "description": "Scan resources and identify tagging violations.",
                "parameters": {
                    "resource_types": resource_types,
                    "severity": "errors_only",
                },
            }
        )

        # Step 2: Apply default tags
        for tag in tags:
            default_value = tag.allowed_values[0] if tag.allowed_values else "unassigned"
            tag_commands = []
            for rt in resource_types:
                if rt.startswith("ec2:") or rt.startswith("rds:"):
                    tag_commands.append(
                        f"aws resourcegroupstaggingapi tag-resources "
                        f"--resource-arn-list {{resource_arn}} "
                        f"--tags {tag.name}={default_value}"
                    )
                else:
                    tag_commands.append(
                        f"aws resourcegroupstaggingapi tag-resources "
                        f"--resource-arn-list {{resource_arn}} "
                        f"--tags {tag.name}={default_value}"
                    )

            steps.append(
                {
                    "name": f"Tag Resources with {tag.name}",
                    "action": "aws_cli",
                    "description": (
                        f"Apply default value '{default_value}' for tag '{tag.name}' "
                        f"to non-compliant resources."
                    ),
                    "script": "\n".join(tag_commands),
                    "on_failure": "continue",
                }
            )

        # Step 3: Verify remediation
        steps.append(
            {
                "name": "Verify Remediation",
                "action": "compliance_check",
                "description": "Re-scan resources to verify tags were applied.",
                "parameters": {
                    "resource_types": resource_types,
                    "severity": "errors_only",
                },
            }
        )

    elif remediation_strategy == "notify":
        # Step 1: Identify violations
        steps.append(
            {
                "name": "Identify Non-Compliant Resources",
                "action": "compliance_check",
                "description": "Scan resources and identify tagging violations.",
                "parameters": {
                    "resource_types": resource_types,
                    "severity": "errors_only",
                },
            }
        )

        # Step 2: Send notification
        steps.append(
            {
                "name": "Notify Resource Owners",
                "action": "notification",
                "description": (
                    "Send notification to resource owners about tagging violations."
                ),
                "parameters": {
                    "channel": "email",
                    "template": "tag_compliance_violation",
                    "recipients": ["resource-owner", "finops-team"],
                    "include_remediation_steps": True,
                },
            }
        )

        # Step 3: Create ticket
        steps.append(
            {
                "name": "Create Remediation Ticket",
                "action": "ticket",
                "description": "Create a ticket for tracking remediation progress.",
                "parameters": {
                    "title": "Tag Compliance Violations - {resource_type}",
                    "priority": "medium",
                    "assignee": "resource-owner",
                    "due_date_days": 7,
                },
            }
        )

    elif remediation_strategy == "report":
        # Step 1: Generate report
        steps.append(
            {
                "name": "Generate Compliance Report",
                "action": "compliance_report",
                "description": "Generate a detailed compliance report.",
                "parameters": {
                    "resource_types": resource_types,
                    "format": "markdown",
                    "include_recommendations": True,
                },
            }
        )

        # Step 2: Export CSV
        steps.append(
            {
                "name": "Export Violations CSV",
                "action": "export",
                "description": "Export violation data to CSV for analysis.",
                "parameters": {
                    "format": "csv",
                    "columns": [
                        "resource_arn",
                        "resource_type",
                        "violation",
                        "severity",
                        "region",
                    ],
                },
            }
        )

        # Step 3: Distribute report
        steps.append(
            {
                "name": "Distribute Report",
                "action": "notification",
                "description": "Send the compliance report to stakeholders.",
                "parameters": {
                    "channel": "email",
                    "recipients": ["finops-team", "management"],
                    "attach_report": True,
                },
            }
        )

    workflow["steps"] = steps

    # Metadata
    workflow["metadata"] = {
        "generated_by": "finops-tag-compliance-mcp",
        "generated_at": datetime.utcnow().isoformat() + "Z",
        "target_tags": target_tag_names,
        "threshold": threshold,
    }

    return workflow
