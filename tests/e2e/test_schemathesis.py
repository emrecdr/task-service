"""Property-based OpenAPI tests via Schemathesis 4.x.

Loads the live OpenAPI schema from the in-process FastAPI app (ASGI mode —
no running container required) and generates request cases for every
(method, path) pair. Each generated case must:

- Not return 5xx (server-side faults are bugs, even on bad input).
- Conform to the response schema declared in the spec.
- Reject schema-violating inputs (``negative_data_rejection``).

Marked ``e2e`` so the default ``pytest`` invocation (driven by ``-m "not e2e"``
in ``pyproject.toml``) skips it; run explicitly with ``make schemathesis``.

The built-in ``positive_data_acceptance`` check is excluded: its data
generator does not reliably respect integer ``maximum`` / ``format: int64``
bounds on path parameters and serializes nullable enum query parameters as
the literal string ``"null"``, producing false-positive "rejected positive
data" reports. The semantic equivalent of this check — that schema-compliant
inputs receive 2xx — is covered by the integration suite under
``tests/integration/services/tasks/`` (every endpoint has explicit happy-path
assertions). The remaining checks (no 5xx, schema conformance, negative-data
rejection) catch the higher-value failures and are kept on.
"""

import pytest
import schemathesis
from app.main import app
from schemathesis.specs.openapi.checks import positive_data_acceptance

schema = schemathesis.openapi.from_asgi("/openapi.json", app)

_EXCLUDED_CHECKS = [positive_data_acceptance]


@pytest.mark.e2e
@schema.parametrize()
def test_no_5xx_and_schema_conformance(case: schemathesis.Case) -> None:
    case.call_and_validate(excluded_checks=_EXCLUDED_CHECKS)
