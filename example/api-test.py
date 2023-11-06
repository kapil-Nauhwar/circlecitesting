import os

import schemathesis
from hypothesis import Phase, settings
from schemathesis.checks import not_a_server_error

schema = schemathesis.from_path(
    os.environ.get("OPENAPI_PATH"), base_url=f"http://localhost:{os.environ.get('PORT')}"
)


def before_generate_case(context, strategy):
    """
    This function manipulates the schema prior to it's testing

    Parameters
    ----------
    context
    strategy

    Returns
    -------

    """

    # contains the schema info of the endpoint and all it's dependencies, mentioned in the OpenAPI
    operation = context.operation

    # print(f"operation data\n{operation}")

    def tune_case(case):
        """
        This function injects the example mentioned in the OpenAPI to the case

        Parameters
        ----------
        case: a bare-bone object of the endpoint to be manipulated

        Returns
        -------

        """

        if operation.path_parameters.example:
            case.path_parameters = operation.path_parameters.example
        if operation.body.example:
            case.body = operation.body.example

        return case

    return strategy.map(tune_case)


@settings(deadline=None, phases=[Phase.explicit])
@schema.parametrize()
@schema.hooks.apply(before_generate_case)
def test_api(case, auth_token):
    """

    Parameters
    ----------
    case

    Returns
    -------

    """

    # explicitly adding headers here
    case.headers["X-APi-Key"] = auth_token
    # print(f"case\n{case.__dict__}")
    response = case.call(timeout=60)  # triggers API
    # print("response", response)

    case.validate_response(response, checks=(not_a_server_error,))
