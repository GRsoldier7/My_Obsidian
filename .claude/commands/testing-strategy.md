---
name: testing-strategy
description: |
  Expert testing strategist for Python applications using pytest. Designs test suites that catch real bugs without becoming maintenance burdens. Covers: fixture design, parametrize patterns, property-based testing with hypothesis, integration vs unit test decisions, async testing, database testing patterns, and coverage strategy. Use when writing tests for new code, deciding what to test, debugging a flaky test, improving test coverage, or asking whether an approach is testable. Trigger phrases: "write tests for this", "how should I test this", "test coverage", "pytest fixtures", "hypothesis testing", "flaky test", "integration test vs unit test", "how do I test async code", "mock vs real".
metadata:
  author: aaron-deyoung
  version: "1.0"
  domain-category: engineering
  adjacent-skills: code-review, database-design, biohacking-data-pipeline
  source-repo: GRsoldier7/My_AI_Skills
---

# Testing Strategy — Expert Skill

## Test Value Hierarchy (write in this priority order)

1. **Tests preventing data corruption** — anything writing to DB, modifying shared state, sending external requests
2. **Tests for critical paths** — login, data ingestion, core API endpoints
3. **Tests for edge cases in pure functions** — validation, transformation, business rules (cheap + fast)
4. **Tests for integration points** — does code work with real DB, real API, real filesystem?
5. **Tests for error paths** — does it fail correctly? Right error, rollback, logging?

## The Unit/Integration Decision

**Unit test when:** Self-contained logic, pure/mockable function, runs in <10ms

**Integration test when:** Correctness depends on how components interact, especially with DB

**The rule:** If touching PostgreSQL → use a real test database. Mocking SQLAlchemy tests that you called the mock correctly, not that your SQL works.

## Key Patterns

### Transaction-Rollback Test Isolation (5-20x faster than teardown)
```python
@pytest.fixture
def db_session(db_engine):
    connection = db_engine.connect()
    transaction = connection.begin()
    session = Session(bind=connection)
    yield session
    session.close()
    transaction.rollback()
    connection.close()
```

### Hypothesis for Edge Case Discovery
```python
from hypothesis import given, strategies as st

@given(st.text(min_size=1, max_size=100))
def test_supplement_name_normalization_handles_any_string(name: str):
    result = normalize_supplement_name(name)
    assert isinstance(result, str)
    assert len(result) <= 100
```
Hypothesis finds the boundaries you missed. Let it shrink failures to minimal examples.

### Parametrize for Equivalence Classes
```python
@pytest.mark.parametrize("dosage,expected_unit", [
    ("500mg", "mg"),
    ("1g", "g"),
    ("2.5 mcg", "mcg"),
    ("1000 IU", "IU"),
])
def test_parse_dosage_extracts_unit(dosage, expected_unit):
    assert parse_dosage(dosage).unit == expected_unit
```

### Async FastAPI Testing
```python
@pytest.fixture
async def client(app):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c
```

## Anti-Patterns

1. **Mocking the Database:** Tests pass, queries are wrong, production fails. Use real test DB + transaction-rollback.
2. **The God Fixture:** 15 DB records + 3 API mocks + 2 env vars in one fixture. Each fixture provides exactly what ONE test needs.
3. **Asserting Implementation, Not Behavior:** `assert mock_session.add.call_count == 1` vs. actually querying the DB to confirm the user was saved.
4. **100% Coverage Cargo Cult:** Gaming coverage instead of writing meaningful assertions. Target 80% on critical paths with assertions that would catch real failures.

## Quality Gates
- [ ] Every critical path has at least one integration test against a real database
- [ ] No test uses unittest.mock.patch on SQLAlchemy session or connection
- [ ] Fixtures use transaction-rollback pattern for database tests
- [ ] Async endpoint tests use httpx.AsyncClient with ASGITransport
- [ ] External HTTP calls intercepted at transport layer, not mocked at client level
- [ ] All assertions have failure messages making the cause self-evident
- [ ] Time-dependent code uses injected time or freezegun
