"""Safe read/write helpers for domain entries in infrastructure.json."""

import json
import os
import tempfile
from pathlib import Path
from typing import Any


def _load_infrastructure(infrastructure_path: str | Path | None):
    if not infrastructure_path:
        raise ValueError("No se proporcionó la ruta del archivo de infraestructura.")

    path = Path(infrastructure_path)
    if not path.is_file():
        raise FileNotFoundError(
            f"No se encontró el archivo de infraestructura: {path}"
        )

    with path.open("r", encoding="utf-8") as file:
        data = json.load(file)

    if not isinstance(data, list):
        raise ValueError("La raíz de infrastructure.json debe ser una lista.")

    return path, data


def _find_domain(
    data: list[Any],
    domain_id: int | None,
    current_name: str,
) -> dict[str, Any]:
    for superdomain in data:
        if not isinstance(superdomain, dict):
            continue

        domains = superdomain.get("domains", [])
        if not isinstance(domains, list):
            continue

        for domain in domains:
            if not isinstance(domain, dict):
                continue

            matches = (
                domain.get("id") == domain_id
                if domain_id is not None
                else domain.get("domain") == current_name
            )
            if matches:
                return domain

    identity = (
        f"con id '{domain_id}'"
        if domain_id is not None
        else f"con nombre '{current_name}'"
    )
    raise ValueError(f"No se encontró el dominio {identity} en infrastructure.json.")


def read_domain_property(
    infrastructure_path: str | Path | None,
    domain_id: int | None,
    current_name: str,
    property_name: str,
) -> str:
    """Read a domain property, returning an empty string when it is absent."""
    _, data = _load_infrastructure(infrastructure_path)
    domain = _find_domain(data, domain_id, current_name)
    value = domain.get(property_name, "")
    return "" if value is None else str(value)


def update_domain_property(
    infrastructure_path: str | Path | None,
    domain_id: int | None,
    current_name: str,
    property_name: str,
    value: str,
) -> None:
    """Update one domain property and atomically replace infrastructure.json."""
    path, data = _load_infrastructure(infrastructure_path)
    domain = _find_domain(data, domain_id, current_name)
    domain[property_name] = value

    temporary_path = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            newline="\n",
            dir=path.parent,
            prefix=f".{path.name}.",
            suffix=".tmp",
            delete=False,
        ) as temporary_file:
            temporary_path = Path(temporary_file.name)
            json.dump(data, temporary_file, indent=2, ensure_ascii=False)
            temporary_file.write("\n")

        os.replace(temporary_path, path)
    finally:
        if temporary_path is not None and temporary_path.exists():
            temporary_path.unlink()
