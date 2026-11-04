"""Shared year metadata helpers used by year dialogs and creation flows."""

import json
from pathlib import Path


def calculate_id_package_default(year: int, infra_path: Path = None) -> str:
    """
    Calcula el ID de paquete por defecto basado en las reglas:
    - Primeros dos caracteres del último nombre del superdominio en mayúsculas.
    - "-"
    - Número del dominio dentro del superdominio en dos dígitos.
    - "-"
    - prefix en dos dígitos: {max(0, year - 2003):02d}
    - "-"
    - "00A" al ser default variant key (se pone por defecto)
    """
    if infra_path is None:
        infra_path = Path("__structure__/infrastructure.json")
    if not infra_path.exists():
        return ""
    try:
        with open(infra_path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except Exception:
        return ""

    for sd_data in data:
        sd_name = sd_data.get("superdomain", "").strip()
        for idx, domain_data in enumerate(sd_data.get("domains", [])):
            range_text = domain_data.get("range", "")
            try:
                start_year, end_year = map(int, range_text.split("-"))
            except Exception:
                continue
            if start_year <= year <= end_year:
                # 1. Prefijo del superdominio: primeros dos caracteres del último nombre
                parts = [p for p in sd_name.split("_") if p]
                last_part = parts[-1] if parts else ""
                sd_prefix = last_part[:2].upper()

                # 2. Número del dominio dentro del superdominio (1-based index) en dos dígitos
                domain_index = idx + 1
                dom_index_str = f"{domain_index:02d}"

                # 3. Prefix en dos dígitos
                prefix_str = f"{max(0, year - 2003):02d}"

                # 4. Combinar con default variant key "00A"
                return f"{sd_prefix}-{dom_index_str}-{prefix_str}-00A"
    return ""
