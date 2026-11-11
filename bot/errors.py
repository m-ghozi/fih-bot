from __future__ import annotations

import logging

from discord import app_commands
from discord.ext import commands

from .wiki import PageNotFoundError, WikiError

log = logging.getLogger(__name__)


def describe_command_error(error: BaseException) -> str:
    """Return a user-friendly message for a command error."""
    # Unwrap CommandInvokeError / HybridCommandError layers.
    original = getattr(error, "original", None)
    while original is not None and original is not error:
        error = original
        original = getattr(error, "original", None)

    if isinstance(error, (commands.CommandOnCooldown, app_commands.CommandOnCooldown)):
        return f"Slow down. Try again in **{error.retry_after:.1f} seconds**."
    if isinstance(error, PageNotFoundError):
        return str(error)
    if isinstance(error, WikiError):
        return f"Failed to fetch data from the wiki: {error}"

    log.error("Unhandled command error: %r", error)
    return "Something went wrong. Please try again in a moment."
