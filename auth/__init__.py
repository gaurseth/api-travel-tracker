"""
Authentication module for Travel Tracker API.
"""
from .firebase_auth import (
    get_current_user,
    init_firebase,
    verify_internal_api_key,
    resolve_user_by_email,
)

__all__ = [
    "get_current_user",
    "init_firebase",
    "verify_internal_api_key",
    "resolve_user_by_email",
]
