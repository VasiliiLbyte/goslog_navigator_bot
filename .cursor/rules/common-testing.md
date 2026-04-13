# Testing Requirements

## Coverage Targets by Risk

- **quick-fix:** add targeted regression tests for changed behavior.
- **feature:** prefer 80%+ coverage in affected module(s), with unit + integration coverage as appropriate.
- **critical:** target 80%+ coverage and include end-to-end validation for critical user flows.

Test Types:
1. **Unit Tests** - Individual functions, utilities, components
2. **Integration Tests** - API endpoints, database operations
3. **E2E Tests** - Critical user flows (framework chosen per language)

## Test-Driven Development

Default workflow:
1. Write test first (RED)
2. Run test - it should FAIL
3. Write minimal implementation (GREEN)
4. Run test - it should PASS
5. Refactor (IMPROVE)
6. Verify coverage target for task profile

## Troubleshooting Test Failures

1. Use **tdd-guide** agent
2. Check test isolation
3. Verify mocks are correct
4. Fix implementation, not tests (unless tests are wrong)

## Agent Support

- **tdd-guide** - Use PROACTIVELY for feature/critical changes, enforces write-tests-first
