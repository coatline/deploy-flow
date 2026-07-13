from __future__ import annotations

import keyring

SERVICE_NAME = "deployflow"


def store_credential(key: str, value: str) -> None:
    keyring.set_password(SERVICE_NAME, key, value)


def load_credential(key: str) -> str:
    return keyring.get_password(SERVICE_NAME, key) or ""


def delete_credential(key: str) -> None:
    try:
        keyring.delete_password(SERVICE_NAME, key)
    except keyring.errors.PasswordDeleteError:
        pass
