#!/usr/bin/env python3
"""Cross-platform bootstrapper for the local Who could MVP."""

from __future__ import annotations

import platform
import os
import shutil
import secrets
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parent


def run(*command: str, cwd: Path | None = None) -> None:
    print("+", " ".join(command))
    subprocess.run(command, cwd=cwd, check=True)


def command_version(command: str, *args: str) -> tuple[int, ...]:
    output = subprocess.check_output(
        [command, *args], text=True, stderr=subprocess.STDOUT
    ).strip()
    version = output.removeprefix("v").split()[0]
    return tuple(int(part) for part in version.split(".")[:3])


def validate_runtime() -> tuple[str, str]:
    python = shutil.which("python3") or shutil.which("python")
    if not python:
        raise SystemExit(
            "Python не найден. Установите Python 3.10 или новее: https://python.org/downloads/"
        )
    if command_version(python, "--version") < (3, 10):
        raise SystemExit(
            "Нужен Python >= 3.10. Обновите Python и повторите запуск install.py."
        )
    try:
        subprocess.run(
            [python, "-m", "venv", "--help"],
            check=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
    except subprocess.CalledProcessError as exc:
        raise SystemExit(
            "Модуль venv недоступен. Установите python3-venv (Linux) или полный Python installer."
        ) from exc
    node, npm = shutil.which("node"), shutil.which(
        "npm.cmd" if platform.system() == "Windows" else "npm"
    )
    if not node:
        raise SystemExit(
            "Node.js не найден. Для Vite 8 установите Node.js >= 20.19 (рекомендуется LTS 22)."
        )
    node_version = command_version(node, "--version")
    if node_version < (20, 19) or node_version[0] == 21:
        raise SystemExit(
            f"Node.js {'.'.join(map(str, node_version))} несовместим. Установите LTS 22 (минимум 20.19)."
        )
    if not npm:
        raise SystemExit("npm не найден. Переустановите Node.js вместе с npm.")
    return python, npm


def main() -> None:
    python, npm = validate_runtime()
    venv = ROOT / "backend" / ".venv"
    if not venv.exists():
        run(python, "-m", "venv", str(venv))
    venv_python = venv / (
        "Scripts/python.exe" if platform.system() == "Windows" else "bin/python"
    )
    run(
        str(venv_python),
        "-m",
        "pip",
        "install",
        "-r",
        "requirements.txt",
        cwd=ROOT / "backend",
    )
    run(npm, "ci", cwd=ROOT / "frontend")
    env_file = ROOT / "backend" / ".env"
    if not env_file.exists():
        env_file.write_text(
            (ROOT / "backend" / ".env.example").read_text(encoding="utf-8")
            + f"\nWHO_COULD_SECRET={secrets.token_urlsafe(48)}\n",
            encoding="utf-8",
        )
        env_file.chmod(0o600)
        if not any(
            os.getenv(k)
            for k in ("DATABASE_URL", "DATABASE_PASSWORD", "DATABASE_PASSWORD_FILE")
        ):
            raise SystemExit(
                "Создан backend/.env. Укажите подключение к отдельной MariaDB и DATABASE_PASSWORD, затем повторите python install.py. База данных автоматически не создаётся."
            )
    run(str(venv_python), "-m", "alembic", "upgrade", "head", cwd=ROOT / "backend")
    print(
        "\nГотово. Запускайте сервисы отдельно из папки scripts/ или вместе через run-project."
    )


if __name__ == "__main__":
    main()
