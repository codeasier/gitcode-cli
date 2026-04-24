from typing import Optional


class GCError(Exception):
    pass


class ConfigError(GCError):
    pass


class AuthError(GCError):
    pass


class RepoResolutionError(GCError):
    pass


class APIError(GCError):
    def __init__(self, message: str, status_code: Optional[int] = None):
        super().__init__(message)
        self.status_code = status_code
