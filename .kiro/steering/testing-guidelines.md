# Testing Guidelines

## Test Types

### Unit Tests (`tests/unit/`)
- Test individual functions and classes in isolation
- Mock external dependencies (AWS, Redis)
- Use `moto` for AWS mocking
- Fast execution (< 1 second per test)

### Property Tests (`tests/property/`)
- Use Hypothesis for property-based testing
- Minimum 100 iterations per property
- Tag each test with the property it validates:
  ```python
  def test_compliance_score_bounds():
      """
      Feature: phase-1-aws-mvp, Property 1: Compliance Score Bounds
      Validates: Requirements 1.1
      """
  ```
- Focus on universal properties, not specific examples

### Integration Tests (`tests/integration/`)
- Mark with `@pytest.mark.integration`
- Test end-to-end flows
- May require real AWS credentials (test account)
- Run separately from unit tests

## Running Tests

```bash
# Full regression suite
pytest tests/

# Unit tests only (fast)
pytest tests/unit/

# Property tests only
pytest tests/property/

# Integration tests only
pytest tests/integration/ -m integration

# With coverage
pytest tests/ --cov=mcp_server --cov-report=html
```

## Coverage Target
- 80% code coverage for unit tests
- All 13 correctness properties must have property tests

## Test Naming
- `test_<function_name>_<scenario>` for unit tests
- `test_property_<property_number>_<short_name>` for property tests
