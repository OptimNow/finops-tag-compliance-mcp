# Testing Quick Start Guide

## Running Tests

### All Tests
```bash
python run_tests.py
```

### By Type
```bash
python run_tests.py --unit          # Unit tests only
python run_tests.py --property      # Property tests only
python run_tests.py --integration   # Integration tests only
```

### Fast Mode (Skip Slow Tests)
```bash
python run_tests.py --fast
```

### With Coverage Report
```bash
python run_tests.py --coverage
```

### Specific Tests
```bash
python run_tests.py --keyword "compliance"  # Tests matching keyword
python run_tests.py --markers "unit"        # Tests with marker
```

### Debug Mode
```bash
python run_tests.py --verbose       # Verbose output
python run_tests.py --failfast      # Stop on first failure
python run_tests.py --pdb           # Drop into debugger on failure
```

## Using pytest Directly

```bash
# All tests
pytest tests/

# Specific file
pytest tests/unit/test_compliance.py

# Specific test
pytest tests/unit/test_compliance.py::TestComplianceService::test_score

# With coverage
pytest tests/ --cov=mcp_server --cov-report=html

# Verbose
pytest tests/ -vv

# Show print statements
pytest tests/ -s

# Stop on first failure
pytest tests/ -x

# Drop into debugger
pytest tests/ --pdb
```

## Test Structure

```
tests/
├── unit/           # Fast isolated tests (mock dependencies)
├── property/       # Property-based tests (Hypothesis)
└── integration/    # End-to-end tests (real dependencies)
```

## Writing Tests

### Unit Test Example
```python
# tests/unit/test_compliance.py
import pytest
from mcp_server.services import ComplianceService

class TestComplianceService:
    def test_compliance_score_calculation(self, mock_aws_client):
        service = ComplianceService(aws_client=mock_aws_client)
        result = service.calculate_compliance_score()
        assert 0.0 <= result <= 1.0
```

### Property Test Example
```python
# tests/property/test_compliance.py
from hypothesis import given, strategies as st

class TestComplianceProperties:
    @given(total=st.integers(min_value=0, max_value=10000))
    def test_compliance_score_bounds(self, total):
        """
        Feature: phase-1-aws-mvp, Property 1: Compliance Score Bounds
        Validates: Requirements 1.1
        """
        score = calculate_score(0, total)
        assert 0.0 <= score <= 1.0
```

## Available Fixtures

```python
# Environment
test_env                    # Test environment variables

# Mocks
mock_aws_client            # Mock AWS client
mock_redis_client          # Mock Redis client
mock_sqlite_connection     # Mock SQLite connection

# Test Data
sample_violation_data      # Sample violation
sample_compliance_result   # Sample compliance result
sample_tagging_policy      # Sample tagging policy
sample_resource_data       # Sample AWS resource data
```

## Coverage

Generate HTML coverage report:
```bash
pytest tests/ --cov=mcp_server --cov-report=html
# Open htmlcov/index.html in browser
```

Target: 80% code coverage

## Markers

```bash
pytest tests/ -m unit              # Unit tests only
pytest tests/ -m property          # Property tests only
pytest tests/ -m integration       # Integration tests only
pytest tests/ -m "not integration" # Exclude integration tests
pytest tests/ -m "not slow"        # Exclude slow tests
```

## Troubleshooting

**Tests are slow:**
```bash
python run_tests.py --fast
```

**Tests are failing:**
```bash
python run_tests.py --verbose --failfast
```

**Need more details:**
```bash
python run_tests.py --pdb
```

**Clear Hypothesis cache:**
```bash
rm -rf .hypothesis/
```

## CI/CD Integration

GitHub Actions example:
```yaml
- name: Run tests
  run: python run_tests.py --coverage
```

## More Information

See `tests/README.md` for comprehensive documentation.
