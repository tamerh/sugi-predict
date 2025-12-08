# BioYoda Agent Testing

Simple testing setup for iterative development.

## Files

```
tests/
  cli.py           # Interactive CLI for manual testing
  runner.py        # Automated test runner
  test_cases.yaml  # All test cases
  README.md        # This file
```

**Do not add new test files.** Modify existing ones or add cases to `test_cases.yaml`.

## Usage

### Manual Testing
```bash
# Interactive mode
python cli.py

# Single query
python cli.py "What is the protein for TP53?"
```

### Automated Tests
```bash
# List available tests
python runner.py --list

# Run single test (partial name match)
python runner.py -t "reverse"
python runner.py -t "single gene"

# Run section
python runner.py --section biobtree_queries

# Quick smoke test (subset)
python runner.py --quick

# Full suite (run only when ready)
python runner.py
```

## Adding Tests

Edit `test_cases.yaml`:

```yaml
biobtree_queries:
  - name: "My new test"
    query: "Map KRAS to UniProt"
    expect_tool: biobtree_query      # or false for direct answer
    expect_contains: ["P01116"]       # strings to find in result
    expect_mapped: 1                  # minimum mapped count
```

## Workflow

1. Develop feature → `python cli.py "query"`
2. Add test case → edit `test_cases.yaml`
3. Verify test → `python runner.py -t "test name"`
4. Final check → `python runner.py`
