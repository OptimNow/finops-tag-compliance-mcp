# MCP Tool Implementation Patterns

When implementing MCP tools, follow this consistent pattern.

## Tool Structure

```python
from mcp import tool
from ..models import SomeResult
from ..services import SomeService

@tool()
async def tool_name(
    required_param: str,
    optional_param: str | None = None
) -> SomeResult:
    """
    Brief description of what the tool does.
    
    Args:
        required_param: What this parameter is for
        optional_param: What this optional parameter does
    
    Returns:
        SomeResult with the relevant data
    """
    # 1. Validate inputs
    if not required_param:
        raise ValueError("required_param cannot be empty")
    
    # 2. Call service layer
    service = SomeService()
    result = await service.do_something(required_param, optional_param)
    
    # 3. Return structured response
    return result
```

## The 8 MCP Tools

1. `check_tag_compliance` - Scan resources and return compliance score
2. `find_untagged_resources` - Find resources missing tags
3. `validate_resource_tags` - Validate specific resources by ARN
4. `get_cost_attribution_gap` - Calculate financial impact of tagging gaps
5. `suggest_tags` - Suggest tag values for a resource
6. `get_tagging_policy` - Return the policy configuration
7. `generate_compliance_report` - Generate formatted reports
8. `get_violation_history` - Return historical compliance data

## Key Principles

- Tools are thin wrappers around services
- All business logic lives in services
- Tools handle input validation and response formatting
- Use Pydantic models for all inputs and outputs
- Log every tool invocation for audit trail
