"""
Single-login enforcement middleware.

When a user logs in, their current session key is stored on the User model's
last_session_key field.  On every subsequent request the middleware checks
whether the stored key still matches the active session.  If a different device
has logged in with the same credentials, the older session is considered stale
and is expired immediately.

This allows two project sites to be active at the same time while ensuring each
user account can only be authenticated in one browser session at any time.

Requirements:
  - The User model must have a `last_session_key` CharField (see accounts migration).
  - Add 'core.middleware.SingleLoginMiddleware' to settings.MIDDLEWARE after
    'django.contrib.auth.middleware.AuthenticationMiddleware'.
"""

from django.contrib.auth import logout
from django.contrib import messages


class SingleLoginMiddleware:
    """Expire any earlier session when the same user logs in elsewhere."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if (
            request.user.is_authenticated
            and hasattr(request.user, "last_session_key")
            and request.user.last_session_key
            and request.session.session_key
            and request.user.last_session_key != request.session.session_key
        ):
            # A newer session exists for this user — invalidate the current one
            logout(request)
            messages.warning(
                request,
                "You have been signed out because your account was logged in from another device or browser.",
            )
            from django.shortcuts import redirect
            return redirect("login")

        response = self.get_response(request)
        return response
