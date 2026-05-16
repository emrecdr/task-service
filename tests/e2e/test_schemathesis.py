"""Property-based OpenAPI tests via Schemathesis (ASGI in-process).

Run with ``make schemathesis``. ``positive_data_acceptance`` is excluded
because its generator mis-bounds integer path params and emits ``"null"``
for nullable enums; happy-path coverage lives in ``tests/integration``.
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
