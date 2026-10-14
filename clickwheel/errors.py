"""The one error type routes raise: a status, a short title, one line of advice."""


class AppError(Exception):
    def __init__(self, status: int, title: str, message: str, detail: str = ""):
        super().__init__(title)
        self.status, self.title, self.message, self.detail = status, title, message, detail


def error_body(title: str, message: str, detail: str = "") -> dict:
    return {"error": {"title": title, "message": message, "detail": detail}}
