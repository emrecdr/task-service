"""Property-based OpenAPI tests via Schemathesis 4.x.

Loads the live OpenAPI schema from the in-process FastAPI app (ASGI mode —
no running container required) and generates request cases for every
(method, path) pair. Each generated case must:

- Not return 5xx (server-side faults are bugs, even on bad input).
- Conform to the response schema declared in the spec.

Marked ``e2e`` so the default ``pytest`` invocation (driven by ``-m "not e2e"``
in ``pyproject.toml``) skips it; run explicitly with ``make schemathesis``.
"""

import pytest
import schemathesis
from app.main import app

schema = schemathesis.openapi.from_asgi("/openapi.json", app)


@pytest.mark.e2e
@schema.parametrize()
def test_no_5xx_and_schema_conformance(case: schemathesis.Case) -> None:
    case.call_and_validate()
