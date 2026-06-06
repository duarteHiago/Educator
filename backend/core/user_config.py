"""
UserConfig — configuração cifrada para distribuição (.exe).

Em modo dev (sem sys.frozen): init_user_config() é no-op, .env é usado normalmente.
Em modo distribuído (sys.frozen=True): lê config.enc ou executa wizard no primeiro uso.

Chave de cifração: SHA-256(hostname) → base64url → Fernet key (32 bytes).
Isso vincula o config.enc à máquina onde foi criado.
"""
from __future__ import annotations

import base64
import getpass
import hashlib
import json
import os
import socket
import sys
from dataclasses import asdict, dataclass
from pathlib import Path

from cryptography.fernet import Fernet, InvalidToken

# URL do proxy VPS — alterar antes de buildar nova versão do .exe
_PROXY_URL = "http://72.60.150.220:4000"


@dataclass
class UserConfig:
    cpf: str
    ava_password: str
    proxy_token: str
    proxy_url: str = _PROXY_URL


def _config_file() -> Path:
    if getattr(sys, "frozen", False):
        appdata = os.environ.get("APPDATA") or str(Path.home())
        return Path(appdata) / "Educator" / "config.enc"
    return Path.home() / ".educator" / "config.enc"


def _derive_key() -> bytes:
    hostname = socket.gethostname().encode()
    digest = hashlib.sha256(hostname).digest()
    return base64.urlsafe_b64encode(digest)


def load() -> UserConfig | None:
    path = _config_file()
    if not path.exists():
        return None
    try:
        raw = path.read_bytes()
        decrypted = Fernet(_derive_key()).decrypt(raw)
        d = json.loads(decrypted.decode())
        return UserConfig(**d)
    except (InvalidToken, KeyError, json.JSONDecodeError):
        return None


def save(config: UserConfig) -> None:
    path = _config_file()
    path.parent.mkdir(parents=True, exist_ok=True)
    encrypted = Fernet(_derive_key()).encrypt(json.dumps(asdict(config)).encode())
    path.write_bytes(encrypted)


def reset() -> None:
    path = _config_file()
    if path.exists():
        path.unlink()


def run_wizard() -> UserConfig:
    print("\n" + "=" * 45)
    print("  EDUCATOR — Configuração Inicial")
    print("=" * 45)
    print()

    cpf = ""
    while not cpf.isdigit() or len(cpf) != 11:
        cpf = input("  CPF (somente números, 11 dígitos): ").strip()
        if not cpf.isdigit() or len(cpf) != 11:
            print("  CPF inválido. Tente novamente.")

    ava_password = ""
    while not ava_password:
        ava_password = getpass.getpass("  Senha AVA: ")

    token = ""
    while not token:
        token = input("  Token de acesso: ").strip()
        if not token:
            print("  Token não pode ser vazio.")

    config = UserConfig(cpf=cpf, ava_password=ava_password, proxy_token=token)
    save(config)

    print()
    print("  Configuração salva com sucesso.")
    print("=" * 45 + "\n")
    return config


def init_user_config() -> UserConfig | None:
    """
    Carrega config.enc e injeta no os.environ antes de Settings() ser instanciado.
    Deve ser chamado no entry point, antes de qualquer import de backend.*.
    Em modo dev (não-frozen), é no-op.
    """
    if not getattr(sys, "frozen", False):
        return None

    config = load()
    if config is None:
        config = run_wizard()

    os.environ["PORTAL_USERNAME"] = config.cpf
    os.environ["PORTAL_PASSWORD"] = config.ava_password
    os.environ["PROXY_URL"] = config.proxy_url
    os.environ["PROXY_TOKEN"] = config.proxy_token

    return config
