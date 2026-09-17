"""Typed errors used across the local console."""


class AppError(Exception):
    code = "APP_ERROR"
    status_code = 500

    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.message = message


class ValidationFailed(AppError):
    code = "VALIDATION_ERROR"
    status_code = 422


class ConflictError(AppError):
    code = "CONFLICT"
    status_code = 409


class NotFoundError(AppError):
    code = "NOT_FOUND"
    status_code = 404


class TaskControlError(AppError):
    code = "TASK_CONTROL_ERROR"
    status_code = 409


class BrowserFlowError(AppError):
    code = "BROWSER_FLOW_ERROR"
    status_code = 500


class GenerationLimitError(BrowserFlowError):
    code = "GENERATION_LIMIT"


class LoginRequiredError(BrowserFlowError):
    code = "LOGIN_REQUIRED"
