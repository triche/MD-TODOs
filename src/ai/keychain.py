"""macOS Keychain helpers for secure API key storage.

Uses the macOS ``security`` CLI to read/write generic passwords.
This keeps API keys out of config files, environment variables, and
source code.

Functions degrade gracefully on non-macOS platforms by raising
``KeychainUnavailableError``.
"""

import logging
import platform
import shutil
import subprocess

logger = logging.getLogger("md_todos.ai.keychain")

_SERVICE_NAME = "md-todos"
_ACCOUNT_NAME = "openai-api-key"


class KeychainError(Exception):
    """Base exception for Keychain operations."""


class KeychainUnavailableError(KeychainError):
    """Raised when the macOS Keychain (``security`` CLI) is not available."""


class KeychainItemNotFoundError(KeychainError):
    """Raised when the requested Keychain item does not exist."""


def _require_security_cli() -> str:
    """Return the path to the ``security`` binary, or raise."""
    if platform.system() != "Darwin":
        msg = "Keychain integration is only available on macOS"
        raise KeychainUnavailableError(msg)
    path = shutil.which("security")
    if path is None:
        msg = "Could not find the macOS `security` command"
        raise KeychainUnavailableError(msg)
    return path


def get_api_key(
    service: str = _SERVICE_NAME,
    account: str = _ACCOUNT_NAME,
) -> str:
    """Retrieve the API key from the macOS Keychain.

    Args:
        service: Keychain service name.
        account: Keychain account name.

    Returns:
        The stored API key string.

    Raises:
        KeychainUnavailableError: Not running on macOS or ``security`` missing.
        KeychainItemNotFoundError: No matching Keychain entry.
        KeychainError: Any other Keychain failure.
    """
    security = _require_security_cli()
    try:
        result = subprocess.run(
            [
                security,
                "find-generic-password",
                "-s",
                service,
                "-a",
                account,
                "-w",  # print password only
            ],
            capture_output=True,
            text=True,
            check=True,
        )
    except subprocess.CalledProcessError as exc:
        # Exit code 44 = item not found
        if exc.returncode == 44:
            msg = f"No Keychain entry for service={service!r} account={account!r}"
            raise KeychainItemNotFoundError(msg) from exc
        stderr = exc.stderr.strip() if exc.stderr else "unknown error"
        msg = f"Keychain lookup failed (rc={exc.returncode}): {stderr}"
        raise KeychainError(msg) from exc

    api_key = result.stdout.strip()
    if not api_key:
        msg = f"Keychain entry for service={service!r} account={account!r} is empty"
        raise KeychainItemNotFoundError(msg)

    logger.debug("Retrieved API key from Keychain (service=%s)", service)
    return api_key


def set_api_key(
    api_key: str,
    service: str = _SERVICE_NAME,
    account: str = _ACCOUNT_NAME,
) -> None:
    """Store (or update) the API key in the macOS Keychain.

    If an entry already exists it is deleted first, then re-created
    (``security add-generic-password`` does not support in-place update).

    Args:
        api_key: The API key to store.
        service: Keychain service name.
        account: Keychain account name.

    Raises:
        KeychainUnavailableError: Not running on macOS or ``security`` missing.
        KeychainError: Any other Keychain failure.
    """
    security = _require_security_cli()

    # Remove existing entry (ignore errors if it doesn't exist)
    subprocess.run(
        [security, "delete-generic-password", "-s", service, "-a", account],
        capture_output=True,
        check=False,
    )

    try:
        subprocess.run(
            [
                security,
                "add-generic-password",
                "-s",
                service,
                "-a",
                account,
                "-w",
                api_key,
                "-U",  # update if exists
            ],
            capture_output=True,
            text=True,
            check=True,
        )
    except subprocess.CalledProcessError as exc:
        stderr = exc.stderr.strip() if exc.stderr else "unknown error"
        msg = f"Failed to store Keychain entry (rc={exc.returncode}): {stderr}"
        raise KeychainError(msg) from exc

    logger.debug("Stored API key in Keychain (service=%s)", service)


def delete_api_key(
    service: str = _SERVICE_NAME,
    account: str = _ACCOUNT_NAME,
) -> bool:
    """Delete the API key from the macOS Keychain.

    Returns:
        *True* if an entry was deleted, *False* if none existed.

    Raises:
        KeychainUnavailableError: Not running on macOS or ``security`` missing.
        KeychainError: Any other Keychain failure.
    """
    security = _require_security_cli()
    result = subprocess.run(
        [security, "delete-generic-password", "-s", service, "-a", account],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode == 0:
        logger.debug("Deleted API key from Keychain (service=%s)", service)
        return True
    if result.returncode == 44:
        logger.debug("No Keychain entry to delete (service=%s)", service)
        return False
    stderr = result.stderr.strip() if result.stderr else "unknown error"
    msg = f"Failed to delete Keychain entry (rc={result.returncode}): {stderr}"
    raise KeychainError(msg)
