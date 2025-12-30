# Test Infrastructure

This directory contains the complete test suite for the FinOps Tag Compliance MCP Server.

## Directory Structure

```
tests/
├── unit/                    # Fast, isolated unit tests
├── property/                # Property-based tests using Hypothesis
├── integration/             # End-to-end integration tests
├── conftest.py              # Pytest configuration and shared fixtures
└── README.md                # This file
```

## Test Types

### Unit Tests (`tests/unit/`)

Fast, isolated tests that verify individual functions and classes in isolation.

- **Speed**: < 1 second per test
- **Dependencies**: Mocked (AWS, Redis, SQLite)
- **Coverage**: Core business logic
- **Tools**: pytest, moto (for AWS mocking)

Example:
```bash
pytest tests/unit/ -v
```

### Property-Based Tests (`tests/property/`)

Tests that verify universal properties hold across many randomly generated inputs.

- **Framework**: Hypothesis
- **Iterations**: Minimum 100 per property
- **Coverage**: Correctness properties from design document
- **Validation**: Pydantic models, data transformations

Example:
```bash
pytest tests/property/ -v
```

### Integration Tests (`tests/integration/`)

End-to-end tests that verify complete workflows.

- **Scope**: Full system behavior
- **Dependencies**: May require real AWS credentials (test account)
- **Speed**: Slower (can take minutes)
- **Marker**: `@pytest.mark.integration`

Example:
```bash
pytest tests/integration/ -v -m integration
```

## Running Tests

### Quick Start

Run all tests:
```bash
python run_tests.py
```

Or on Unix-like systems:
```bash
./run_tests.sh
```

Or on Windows:
```bash
run_tests.bat
```

### Common Commands

**Run unit tests only (fast):**
```bash
python run_tests.py --unit
```

**Run property tests only:**
```bash
python run_tests.py --property
```

**Run with coverage report:**
```bash
python run_tests.py --coverage
```

**Run fast tests (exclude slow/integration):**
```bash
python run_tests.py --fast
```

**Run specific test by keyword:**
```bash
python run_tests.py --keyword "compliance_score"
```

**Run with verbose output:**
```bash
python run_tests.py --verbose
```

**Stop on first failure:**
```bash
python run_tests.py --failfast
```

**Drop into debugger on failure:**
```bash
python run_tests.py --pdb
```

### Using pytest Directly

You can also use pytest directly for more control:

```bash
# Run all tests
pytest tests/

# Run with coverage
pytest tests/ --cov=mcp_server --cov-report=html

# Run specific test file
pytest tests/unit/test_compliance.py

# Run specific test class
pytest tests/unit/test_compliance.py::TestComplianceService

# Run specific test method
pytest tests/unit/test_compliance.py::TestComplianceService::test_score_calculation

# Run with markers
pytest tests/ -m "unit or property"
pytest tests/ -m "not integration"

# Run with keyword filter
pytest tests/ -k "compliance"

# Verbose output
pytest tests/ -vv

# Show print statements
pytest tests/ -s

# Stop on first failure
pytest tests/ -x

# Drop into debugger on failure
pytest tests/ --pdb
```

## Test Configuration

### pytest.ini Configuration

The project uses `pyproject.toml` for pytest configuration:

```toml
[tool.pytest.ini_options]
testpaths = ["tests"]
python_files = ["test_*.py"]
python_classes = ["Test*"]
python_functions = ["test_*"]
asyncio_mode = "auto"
addopts = "--strict-markers"
markers = [
    "integration: marks tests as integration tests",
    "slow: marks tests as slow (deselect with '-m \"not slow\"')",
]
```

### Coverage Configuration

Coverage target: **80% code coverage**

```toml
[tool.coverage.run]
source = ["mcp_server"]
omit = ["*/tests/*", "*/test_*.py"]

[tool.coverage.report]
exclude_lines = [
    "pragma: no cover",
    "def __repr__",
    "raise AssertionError",
    "raise NotImplementedError",
    "if __name__ == .__main__.:",
    "if TYPE_CHECKING:",
]
```

Generate HTML coverage report:
```bash
pytest tests/ --cov=mcp_server --cov-report=html
# Open htmlcov/index.html in browser
```

## Fixtures

Common fixtures are defined in `conftest.py`:

### Environment Fixtures

- `test_env`: Sets up test environment variables

### Mock Fixtures

- `mock_aws_client`: Mock AWS client with common methods
- `mock_redis_client`: Mock Redis client
- `mock_sqlite_connection`: Mock SQLite connection

### Test Data Fixtures

- `sample_violation_data`: Sample violation for testing
- `sample_compliance_result`: Sample compliance result
- `sample_tagging_policy`: Sample tagging policy
- `sample_resource_data`: Sample AWS resource data

Example usage:
```python
def test_something(mock_aws_client, sample_violation_data):
    # Use fixtures in your test
    pass
```

## Writing Tests

### Unit Test Example

```python
# tests/unit/test_compliance.py
import pytest
from mcp_server.services import ComplianceService

class TestComplianceService:
    @pytest.mark.unit
    def test_compliance_score_calculation(self, mock_aws_client):
        """Test that compliance score is calculated correctly."""
        service = ComplianceService(aws_client=mock_aws_client)
        
        # Arrange
        mock_aws_client.describe_instances.return_value = {
            "Reservations": [
                {
                    "Instances": [
                        {"InstanceId": "i-123", "Tags": [{"Key": "Env", "Value": "prod"}]},
                        {"InstanceId": "i-456", "Tags": []},  # Missing tags
                    ]
                }
            ]
        }
        
        # Act
        result = service.calculate_compliance_score()
        
        # Assert
        assert result == 0.5  # 1 compliant out of 2
```

### Property Test Example

```python
# tests/property/test_compliance.py
from hypothesis import given, strategies as st
import pytest

class TestComplianceProperties:
    @given(
        total=st.integers(min_value=0, max_value=10000),
        compliant=st.integers(min_value=0, max_value=10000),
    )
    @pytest.mark.property
    def test_compliance_score_bounds(self, total, compliant):
        """
        Feature: phase-1-aws-mvp, Property 1: Compliance Score Bounds
        Validates: Requirements 1.1
        
        For any set of resources, compliance score must be 0.0-1.0.
        """
        # Ensure compliant <= total
        compliant = min(compliant, total)
        
        score = calculate_score(compliant, total)
        
        assert 0.0 <= score <= 1.0
        if total > 0:
            assert score == compliant / total
```

### Integration Test Example

```python
# tests/integration/test_end_to_end.py
import pytest

@pytest.mark.integration
async def test_full_compliance_check_workflow():
    """Test complete compliance check workflow."""
    # This test might use real AWS credentials (test account)
    # or mocked AWS responses
    pass
```

## Continuous Integration

### GitHub Actions Example

```yaml
name: Tests

on: [push, pull_request]

jobs:
  test:
    runs-on: ubuntu-latest
    strategy:
      matrix:
        python-version: ["3.11", "3.12"]
    
    steps:
      - uses: actions/checkout@v3
      - uses: actions/setup-python@v4
        with:
          python-version: ${{ matrix.python-version }}
      
      - name: Install dependencies
        run: |
          pip install -e ".[dev]"
      
      - name: Run tests
        run: python run_tests.py --coverage
      
      - name: Upload coverage
        uses: codecov/codecov-action@v3
```

## Troubleshooting

### Tests are slow

Run fast tests only:
```bash
python run_tests.py --fast
```

Or run unit tests only:
```bash
python run_tests.py --unit
```

### Tests are failing

Get more details:
```bash
python run_tests.py --verbose --failfast
```

Drop into debugger:
```bash
python run_tests.py --pdb
```

### Coverage is low

Generate HTML report:
```bash
pytest tests/ --cov=mcp_server --cov-report=html
```

Then open `htmlcov/index.html` to see which lines aren't covered.

### Hypothesis tests are flaky

Hypothesis caches examples that fail. Clear the cache:
```bash
rm -rf .hypothesis/
```

Then re-run tests.

## Best Practices

1. **Keep tests focused**: Each test should verify one thing
2. **Use descriptive names**: `test_compliance_score_with_no_resources` is better than `test_score`
3. **Mock external dependencies**: Don't call real AWS APIs in unit tests
4. **Use fixtures**: Share common setup via fixtures
5. **Test edge cases**: Empty lists, None values, boundary conditions
6. **Property tests for universal properties**: Use Hypothesis for rules that should hold for all inputs
7. **Unit tests for specific examples**: Use pytest for concrete test cases
8. **Mark integration tests**: Use `@pytest.mark.integration` for slow tests

## Coverage Goals

- **Unit tests**: 80% code coverage minimum
- **Property tests**: All 13 correctness properties must have tests
- **Integration tests**: Critical workflows and error paths

## Resources

- [pytest documentation](https://docs.pytest.org/)
- [Hypothesis documentation](https://hypothesis.readthedocs.io/)
- [moto documentation](https://docs.getmoto.org/)
- [pytest-asyncio documentation](https://pytest-asyncio.readthedocs.io/)
