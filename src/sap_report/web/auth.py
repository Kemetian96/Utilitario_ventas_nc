"""
Autenticacion ligera basada en JSON. Lee `usuarios.json` (raiz del proyecto
por defecto, override con env SAP_USUARIOS_PATH). Cada usuario tiene:
    - password_hash: hash de Werkzeug
    - modulos: lista de paginas permitidas, o ["*"] para todas.
Las paginas son las mismas que el campo `page` de MODULES en app.py.
"""
from __future__ import annotations

import json
import os
from functools import wraps
from pathlib import Path
from typing import Any

from flask import redirect, request, session, url_for
from werkzeug.security import check_password_hash, generate_password_hash


def _ruta_usuarios() -> Path:
    override = os.environ.get("SAP_USUARIOS_PATH")
    if override:
        return Path(override)
    # raiz del proyecto: 4 niveles arriba de este archivo
    return Path(__file__).resolve().parents[3] / "usuarios.json"


def cargar_usuarios() -> dict[str, dict[str, Any]]:
    path = _ruta_usuarios()
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def autenticar(username: str, password: str) -> dict[str, Any] | None:
    """Compara el usuario ignorando mayusculas/minusculas. Devuelve el dict del
    usuario con 'username' canonico (como aparece en usuarios.json)."""
    usuarios = cargar_usuarios()
    username_norm = username.strip().casefold()
    for nombre_canonico, user in usuarios.items():
        if nombre_canonico.casefold() == username_norm \
                and check_password_hash(user["password_hash"], password):
            return {"username": nombre_canonico, **user}
    return None


def usuario_actual() -> str | None:
    return session.get("user")


def modulos_actuales() -> set[str]:
    return set(session.get("modulos", []))


def tiene_acceso(page: str) -> bool:
    if not usuario_actual():
        return False
    mods = modulos_actuales()
    return "*" in mods or page in mods


def requiere_login(view):
    @wraps(view)
    def wrapper(*args, **kwargs):
        if not usuario_actual():
            return redirect(url_for("login", next=request.path))
        return view(*args, **kwargs)
    return wrapper


def requiere_modulo(page: str):
    def decorador(view):
        @wraps(view)
        def wrapper(*args, **kwargs):
            if not usuario_actual():
                return redirect(url_for("login", next=request.path))
            if not tiene_acceso(page):
                return ("Sin permiso para este módulo.", 403)
            return view(*args, **kwargs)
        return wrapper
    return decorador


def cambiar_password(username: str, nueva_password: str) -> bool:
    """Cambia la contrasena de un usuario en usuarios.json (case-insensitive).
    Devuelve True si el usuario existe y se actualizo."""
    path = _ruta_usuarios()
    usuarios = cargar_usuarios()
    target_key: str | None = None
    username_norm = username.strip().casefold()
    for k in usuarios:
        if k.casefold() == username_norm:
            target_key = k
            break
    if target_key is None:
        return False
    usuarios[target_key]["password_hash"] = generate_password_hash(nueva_password)
    path.write_text(
        json.dumps(usuarios, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    return True


def listar_usuarios() -> list[str]:
    """Devuelve los nombres canonicos de los usuarios."""
    return sorted(cargar_usuarios().keys())
