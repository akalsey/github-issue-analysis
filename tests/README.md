# Test Suite

This directory contains the test suite for the GitHub cycle time analyzer project.

## Test Structure

```
tests/
├── README.md           # This file
├── test_smoke.py       # Quick smoke tests for basic functionality
└── fixtures/           # Test data and expected outputs
```

## Running Tests

### Smoke Tests (Quick Validation)
```bash
# Run basic functionality validation
uv run tests/test_smoke.py
```

### Individual Test Files
```bash
# Run specific test file
uv run tests/test_smoke.py
```

## Test Categories

### Smoke Tests (`test_smoke.py`)
- **Purpose**: Quick validation that core functionality works
- **Scope**: Module imports, basic utility functions, CLI interfaces, service instantiation
- **When to run**: After any code changes, before commits, in CI/CD
- **Runtime**: ~10-15 seconds

## Planned Test Expansion (Phase 3)

According to `refactor-plan.md`, the following test files will be added:

- `test_config.py` - Configuration loading and validation
- `test_issue_classifier.py` - Issue classification logic
- `test_ai_service.py` - AI analysis functionality
- `test_report_generator.py` - Report generation
- `test_utils.py` - Utility functions
- `test_integration.py` - End-to-end integration tests

### Test Data Structure
```
fixtures/
├── sample_issues.json      # Sample GitHub issue data
├── expected_outputs/       # Expected report outputs
│   ├── main_report.md     # Expected main report format
│   └── customer_report.md # Expected customer report format
└── mock_responses/         # Mock AI API responses
```

## Test Philosophy

1. **Smoke Tests**: Fast validation of core functionality
2. **Unit Tests**: Isolated testing of individual functions/classes
3. **Integration Tests**: Testing component interactions
4. **Regression Tests**: Ensuring outputs match expected formats

## CI/CD Integration

The smoke tests are designed to be run in CI/CD pipelines:
- Fast execution (~15 seconds)
- Minimal dependencies
- Clear pass/fail indicators
- Exit codes for automation

## Contributing

When adding new functionality:
1. Run existing smoke tests to ensure no regressions
2. Add appropriate tests for new features
3. Update this README if adding new test categories