from rest_framework import status
from rest_framework.response import Response


def api_success(
    *,
    data=None,
    message="Request completed successfully.",
    status_code=status.HTTP_200_OK,
):
    """
    Standard successful API response.
    """
    return Response(
        {
            "success": True,
            "message": message,
            "data": data,
        },
        status=status_code,
    )


def api_error(
    *,
    code,
    detail,
    message="Unable to process the request.",
    fields=None,
    status_code=status.HTTP_400_BAD_REQUEST,
):
    """
    Standard API error response.
    """
    error = {
        "code": code,
        "detail": detail,
    }

    if fields is not None:
        error["fields"] = fields

    return Response(
        {
            "success": False,
            "message": message,
            "error": error,
        },
        status=status_code,
    )
