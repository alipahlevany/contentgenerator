from rest_framework import status
from rest_framework.exceptions import (
    AuthenticationFailed,
    MethodNotAllowed,
    NotAuthenticated,
    NotFound,
    PermissionDenied,
    Throttled,
    ValidationError,
)
from rest_framework.views import exception_handler


def _normalize_error_details(value):
    """
    Convert DRF ErrorDetail objects recursively into plain
    JSON-serializable strings/lists/dicts.
    """
    if isinstance(value, dict):
        return {
            str(key): _normalize_error_details(item)
            for key, item in value.items()
        }

    if isinstance(value, (list, tuple)):
        return [
            _normalize_error_details(item)
            for item in value
        ]

    return str(value)


def _extract_detail(data, default):
    if isinstance(data, dict):
        detail = data.get("detail")

        if detail is not None:
            return str(detail)

    if isinstance(data, (list, tuple)) and data:
        return str(data[0])

    if isinstance(data, str):
        return data

    return default


def standardized_exception_handler(
    exc,
    context,
):
    """
    Convert DRF exceptions to the project's standard API contract:

    {
        "success": false,
        "message": "...",
        "error": {
            "code": "...",
            "detail": "...",
            "fields": {...}
        }
    }
    """
    response = exception_handler(
        exc,
        context,
    )

    if response is None:
        # Unhandled server exceptions should continue through
        # Django's normal 500 handling/logging.
        return None

    original_data = response.data

    if isinstance(exc, ValidationError):
        response.data = {
            "success": False,
            "message": "Request validation failed.",
            "error": {
                "code": "validation_error",
                "detail": (
                    "The request contains invalid data."
                ),
                "fields": _normalize_error_details(
                    original_data
                ),
            },
        }

        return response

    if isinstance(
        exc,
        (
            NotAuthenticated,
            AuthenticationFailed,
        ),
    ):
        code = "authentication_failed"
        message = "Authentication failed."
        default_detail = (
            "Authentication credentials were not accepted."
        )

    elif isinstance(exc, PermissionDenied):
        code = "permission_denied"
        message = "Permission denied."
        default_detail = (
            "You do not have permission to perform "
            "this action."
        )

    elif isinstance(exc, NotFound):
        code = "not_found"
        message = "Resource not found."
        default_detail = "The requested resource was not found."

    elif isinstance(exc, MethodNotAllowed):
        code = "method_not_allowed"
        message = "Method not allowed."
        default_detail = (
            "The HTTP method is not allowed for this endpoint."
        )

    elif isinstance(exc, Throttled):
        code = "rate_limit_exceeded"
        message = "Rate limit exceeded."
        default_detail = (
            "Too many requests. Please try again later."
        )

    elif response.status_code == status.HTTP_409_CONFLICT:
        code = "conflict"
        message = "Request conflict."
        default_detail = "The request conflicts with current state."

    elif response.status_code == status.HTTP_400_BAD_REQUEST:
        code = "request_error"
        message = "Unable to process the request."
        default_detail = "The request is invalid."

    elif response.status_code == status.HTTP_401_UNAUTHORIZED:
        code = "authentication_failed"
        message = "Authentication failed."
        default_detail = (
            "Authentication credentials were not accepted."
        )

    elif response.status_code == status.HTTP_403_FORBIDDEN:
        code = "permission_denied"
        message = "Permission denied."
        default_detail = (
            "You do not have permission to perform "
            "this action."
        )

    elif response.status_code == status.HTTP_404_NOT_FOUND:
        code = "not_found"
        message = "Resource not found."
        default_detail = "The requested resource was not found."

    elif response.status_code == (
        status.HTTP_405_METHOD_NOT_ALLOWED
    ):
        code = "method_not_allowed"
        message = "Method not allowed."
        default_detail = (
            "The HTTP method is not allowed for this endpoint."
        )

    elif response.status_code == (
        status.HTTP_429_TOO_MANY_REQUESTS
    ):
        code = "rate_limit_exceeded"
        message = "Rate limit exceeded."
        default_detail = (
            "Too many requests. Please try again later."
        )

    else:
        code = "api_error"
        message = "Unable to process the request."
        default_detail = "An API error occurred."

    response.data = {
        "success": False,
        "message": message,
        "error": {
            "code": code,
            "detail": _extract_detail(
                original_data,
                default_detail,
            ),
        },
    }

    return response
