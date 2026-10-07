from rest_framework.views import exception_handler


def api_exception_handler(exc, context):
    response = exception_handler(exc, context)
    if response is None:
        return response

    details = response.data
    code = "VALIDATION_ERROR" if response.status_code == 400 else "REQUEST_ERROR"
    if response.status_code == 409:
        code = "CONFLICT"
    if isinstance(details, dict) and "detail" in details:
        message = str(details["detail"])
        details = {}
    else:
        message = "Please correct the request and try again."

    response.data = {
        "error": {
            "code": code,
            "message": message,
            "details": details,
        }
    }
    return response
