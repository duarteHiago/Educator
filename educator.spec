# educator.spec — PyInstaller 6.x
# Gera dist/educator/ com o educator.exe + dependências em _internal/

import sys
from pathlib import Path
import playwright

_PW_DIR = Path(playwright.__file__).parent

a = Analysis(
    ["backend/cli/__main__.py"],
    pathex=[str(Path(".").resolve())],
    binaries=[
        # Node.js runtime do Playwright (necessário para instalar/usar o browser)
        (str(_PW_DIR / "driver" / "node.exe"), "playwright/driver"),
    ],
    datas=[
        # CLI do Playwright (chamado pelo --install-browser)
        (str(_PW_DIR / "driver" / "package"), "playwright/driver/package"),
        # Prompts versionados da LLM
        ("backend/llm/prompts/versions", "backend/llm/prompts/versions"),
    ],
    hiddenimports=[
        # Playwright
        "playwright.async_api",
        "playwright.sync_api",
        "playwright._impl._playwright",
        "playwright._impl._browser",
        "playwright._impl._browser_context",
        "playwright._impl._page",
        "playwright._impl._locator",
        "playwright._impl._network",
        "playwright._impl._element_handle",
        "playwright._impl._frame",
        # Pydantic / settings
        "pydantic_settings",
        "pydantic_settings.env_settings",
        "pydantic.v1",
        # LLM providers
        "openai",
        "openai._models",
        "anthropic",
        "anthropic._models",
        # Crypto
        "cryptography",
        "cryptography.fernet",
        "cryptography.hazmat.backends",
        "cryptography.hazmat.primitives.hashes",
        "cryptography.hazmat.primitives.kdf.pbkdf2",
        # Logging
        "structlog",
        "structlog.stdlib",
        "structlog.processors",
        # UI
        "rich",
        "rich.console",
        "rich.panel",
        "rich.text",
        "rich.rule",
        "questionary",
        "prompt_toolkit",
        # Async
        "asyncio",
    ],
    hookspath=[],
    runtime_hooks=[],
    excludes=[
        "pytest",
        "IPython",
        "notebook",
        "matplotlib",
        "tkinter",
        "_tkinter",
        "PIL",
    ],
    noarchive=False,
    optimize=0,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="educator",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=True,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=False,
    name="educator",
)
