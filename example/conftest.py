import json

import pytest
import yaml
from schemathesis.schemas import BaseSchema


def pytest_addoption(parser):
    """

    Parameters
    ----------
    parser

    Returns
    -------

    """
    parser.addoption("--auth_token", action="store")


@pytest.fixture(scope="session")
def auth_token(request):
    """

    Parameters
    ----------
    request

    Returns
    -------

    """
    name_value = request.config.option.auth_token
    if name_value is None:
        pytest.skip()
    return name_value
