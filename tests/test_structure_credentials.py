import base64
import json
from datetime import date, timedelta

import pytest

from engines.structure_credentials import StructureGitHubCredentialStore


class FakeCredentialBackend:
    def __init__(self):
        self.value = None

    def write(self, username, token):
        self.value = (username, token)

    def read(self):
        return self.value

    def delete(self):
        self.value = None


def test_token_secret_is_stored_outside_metadata(tmp_path):
    backend = FakeCredentialBackend()
    metadata_path = tmp_path / "structure_github_credentials.json"
    store = StructureGitHubCredentialStore(
        metadata_path=metadata_path,
        credential_backend=backend,
    )
    token = "github_pat_example_secret_value"
    expiration = (date.today() + timedelta(days=90)).isoformat()

    store.save_token(token, "mhz698a", expiration)

    metadata_text = metadata_path.read_text(encoding="utf-8")
    metadata = json.loads(metadata_text)

    assert backend.read() == ("mhz698a", token)
    assert metadata == {"username": "mhz698a", "expires_on": expiration}
    assert token not in metadata_text


def test_git_authentication_is_added_through_environment_not_arguments(tmp_path):
    backend = FakeCredentialBackend()
    store = StructureGitHubCredentialStore(
        metadata_path=tmp_path / "credentials.json",
        credential_backend=backend,
    )
    username = "mhz698a"
    token = "github_pat_example_secret_value"
    backend.write(username, token)
    environment = {
        "GIT_CONFIG_COUNT": "1",
        "GIT_CONFIG_KEY_0": "core.quotePath",
        "GIT_CONFIG_VALUE_0": "false",
    }

    result = store.apply_git_authentication(environment)

    expected = base64.b64encode(
        f"{username}:{token}".encode("utf-8")
    ).decode("ascii")
    assert result["GIT_CONFIG_COUNT"] == "3"
    assert result["GIT_CONFIG_KEY_1"] == (
        "http.https://github.com/.extraheader"
    )
    assert result["GIT_CONFIG_VALUE_1"] == f"AUTHORIZATION: basic {expected}"
    assert result["GIT_CONFIG_KEY_2"] == "credential.helper"
    assert result["GIT_CONFIG_VALUE_2"] == ""
    assert token not in " ".join(result.values())


def test_no_configured_token_leaves_existing_git_authentication_untouched(tmp_path):
    backend = FakeCredentialBackend()
    store = StructureGitHubCredentialStore(
        metadata_path=tmp_path / "credentials.json",
        credential_backend=backend,
    )
    environment = {"GIT_TERMINAL_PROMPT": "0"}

    result = store.apply_git_authentication(environment)

    assert result == {"GIT_TERMINAL_PROMPT": "0"}


def test_token_expiration_must_not_be_in_the_past(tmp_path):
    backend = FakeCredentialBackend()
    store = StructureGitHubCredentialStore(
        metadata_path=tmp_path / "credentials.json",
        credential_backend=backend,
    )
    yesterday = (date.today() - timedelta(days=1)).isoformat()

    with pytest.raises(ValueError, match="posterior"):
        store.save_token("token", "mhz698a", yesterday)


def test_delete_token_removes_secret_and_metadata(tmp_path):
    backend = FakeCredentialBackend()
    metadata_path = tmp_path / "credentials.json"
    store = StructureGitHubCredentialStore(
        metadata_path=metadata_path,
        credential_backend=backend,
    )
    store.save_token(
        "github_pat_secret",
        "mhz698a",
        (date.today() + timedelta(days=30)).isoformat(),
    )

    store.delete_token()

    assert backend.read() is None
    assert not metadata_path.exists()


def test_token_without_expiration_is_recorded_as_none(tmp_path):
    backend = FakeCredentialBackend()
    metadata_path = tmp_path / "credentials.json"
    store = StructureGitHubCredentialStore(
        metadata_path=metadata_path,
        credential_backend=backend,
    )

    store.save_token("github_pat_secret", "mhz698a", None)

    assert json.loads(metadata_path.read_text(encoding="utf-8")) == {
        "username": "mhz698a",
        "expires_on": None,
    }
