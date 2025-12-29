# Project Standards

This project builds a FinOps Tag Compliance MCP Server. Follow these standards for all code.

## Tech Stack
- Python 3.11+
- FastAPI for HTTP/MCP server
- Pydantic for data models and validation
- boto3 for AWS integration
- Redis for caching
- SQLite for audit logs and history
- Hypothesis for property-based testing
- pytest for test runner

## Code Style
- Use type hints everywhere
- Async/await for I/O operations
- Pydantic models for all data structures
- Keep functions small and focused
- Docstrings for public functions

## File Organization
```
mcp_server/
├── __init__.py
├── main.py              # FastAPI app entry point
├── models/              # Pydantic data models
├── services/            # Business logic
├── tools/               # MCP tool implementations
├── clients/             # AWS client wrapper
└── utils/               # Shared utilities

tests/
├── unit/                # Fast isolated tests
├── property/            # Hypothesis property tests
└── integration/         # End-to-end tests
```

## Error Handling
- Use custom exceptions (TagComplianceError, PolicyValidationError, AWSAPIError)
- Log errors with context
- Return meaningful error messages to users
- Never expose internal details in error responses

## AWS Best Practices
- Use IAM instance profile for credentials (never hardcode)
- Implement exponential backoff for rate limits
- Cache API responses in Redis
- Respect API quotas
