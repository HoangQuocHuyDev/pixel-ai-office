class ApplicationError(Exception):
    def __init__(self, status_code: int, error_code: str, message: str, retry_after_seconds: float | None = None) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.error_code = error_code
        self.message = message
        self.retry_after_seconds = retry_after_seconds


class WorkflowFencingError(ApplicationError):
    def __init__(self, message: str = "Workflow execution ownership fencing check failed.") -> None:
        super().__init__(409, "WORKFLOW_FENCING_REJECTED", message)
