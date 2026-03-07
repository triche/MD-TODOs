"""Unit tests for the Keychain helper functions."""

import platform
import subprocess
from unittest.mock import MagicMock, patch

import pytest

from src.ai.keychain import (
    KeychainError,
    KeychainItemNotFoundError,
    KeychainUnavailableError,
    delete_api_key,
    get_api_key,
    set_api_key,
)


class TestKeychainPlatformGuard:
    """Keychain functions should raise on non-macOS platforms."""

    @patch("src.ai.keychain.platform.system", return_value="Linux")
    def test_get_api_key_raises_on_linux(self, _mock: MagicMock) -> None:
        with pytest.raises(KeychainUnavailableError, match="only available on macOS"):
            get_api_key()

    @patch("src.ai.keychain.platform.system", return_value="Linux")
    def test_set_api_key_raises_on_linux(self, _mock: MagicMock) -> None:
        with pytest.raises(KeychainUnavailableError, match="only available on macOS"):
            set_api_key("key")

    @patch("src.ai.keychain.platform.system", return_value="Windows")
    def test_delete_api_key_raises_on_windows(self, _mock: MagicMock) -> None:
        with pytest.raises(KeychainUnavailableError, match="only available on macOS"):
            delete_api_key()


class TestKeychainSecurityMissing:
    """If security CLI not found, raise KeychainUnavailableError."""

    @patch("src.ai.keychain.platform.system", return_value="Darwin")
    @patch("src.ai.keychain.shutil.which", return_value=None)
    def test_get_raises_when_security_missing(self, _which: MagicMock, _sys: MagicMock) -> None:
        with pytest.raises(KeychainUnavailableError, match="security"):
            get_api_key()


@pytest.mark.skipif(platform.system() != "Darwin", reason="macOS only")
class TestGetApiKey:
    """Tests for get_api_key() with mocked subprocess."""

    @patch("src.ai.keychain.subprocess.run")
    def test_returns_key_on_success(self, mock_run: MagicMock) -> None:
        mock_run.return_value = subprocess.CompletedProcess(
            args=[], returncode=0, stdout="sk-test-key-123\n", stderr=""
        )
        key = get_api_key(service="test-svc", account="test-acct")
        assert key == "sk-test-key-123"

    @patch("src.ai.keychain.subprocess.run")
    def test_raises_not_found_on_exit_44(self, mock_run: MagicMock) -> None:
        mock_run.side_effect = subprocess.CalledProcessError(
            returncode=44, cmd=[], output="", stderr="not found"
        )
        with pytest.raises(KeychainItemNotFoundError, match="No Keychain entry"):
            get_api_key(service="test-svc", account="test-acct")

    @patch("src.ai.keychain.subprocess.run")
    def test_raises_error_on_other_failure(self, mock_run: MagicMock) -> None:
        mock_run.side_effect = subprocess.CalledProcessError(
            returncode=1, cmd=[], output="", stderr="some error"
        )
        with pytest.raises(KeychainError, match="Keychain lookup failed"):
            get_api_key(service="test-svc", account="test-acct")

    @patch("src.ai.keychain.subprocess.run")
    def test_raises_not_found_on_empty_result(self, mock_run: MagicMock) -> None:
        mock_run.return_value = subprocess.CompletedProcess(
            args=[], returncode=0, stdout="  \n", stderr=""
        )
        with pytest.raises(KeychainItemNotFoundError, match="empty"):
            get_api_key(service="test-svc", account="test-acct")


@pytest.mark.skipif(platform.system() != "Darwin", reason="macOS only")
class TestSetApiKey:
    """Tests for set_api_key() with mocked subprocess."""

    @patch("src.ai.keychain.subprocess.run")
    def test_set_key_success(self, mock_run: MagicMock) -> None:
        # First call: delete (don't care about result)
        # Second call: add (success)
        mock_run.return_value = subprocess.CompletedProcess(
            args=[], returncode=0, stdout="", stderr=""
        )
        set_api_key("sk-new-key", service="test-svc", account="test-acct")
        assert mock_run.call_count == 2

    @patch("src.ai.keychain.subprocess.run")
    def test_set_key_raises_on_add_failure(self, mock_run: MagicMock) -> None:
        # Delete succeeds, add fails
        def side_effect(*args, **kwargs):
            cmd = args[0] if args else kwargs.get("args", [])
            if "add-generic-password" in cmd:
                raise subprocess.CalledProcessError(returncode=1, cmd=cmd, stderr="add failed")
            return subprocess.CompletedProcess(args=cmd, returncode=0, stdout="", stderr="")

        mock_run.side_effect = side_effect
        with pytest.raises(KeychainError, match="Failed to store"):
            set_api_key("sk-key", service="test-svc", account="test-acct")


@pytest.mark.skipif(platform.system() != "Darwin", reason="macOS only")
class TestDeleteApiKey:
    """Tests for delete_api_key() with mocked subprocess."""

    @patch("src.ai.keychain.subprocess.run")
    def test_delete_returns_true_on_success(self, mock_run: MagicMock) -> None:
        mock_run.return_value = subprocess.CompletedProcess(
            args=[], returncode=0, stdout="", stderr=""
        )
        assert delete_api_key(service="test-svc", account="test-acct") is True

    @patch("src.ai.keychain.subprocess.run")
    def test_delete_returns_false_when_not_found(self, mock_run: MagicMock) -> None:
        mock_run.return_value = subprocess.CompletedProcess(
            args=[], returncode=44, stdout="", stderr=""
        )
        assert delete_api_key(service="test-svc", account="test-acct") is False

    @patch("src.ai.keychain.subprocess.run")
    def test_delete_raises_on_error(self, mock_run: MagicMock) -> None:
        mock_run.return_value = subprocess.CompletedProcess(
            args=[], returncode=1, stdout="", stderr="some error"
        )
        with pytest.raises(KeychainError, match="Failed to delete"):
            delete_api_key(service="test-svc", account="test-acct")
