# domain_visor/models.py

from dataclasses import dataclass, field
import json
import os

@dataclass(eq=False)
class Year:
    value: int
    parent_domain: any = None  # Referencia al objeto Domain padre

    def __repr__(self):
        return f"Year({self.value})"


@dataclass(eq=False)
class Domain:
    id: int
    name: str
    range_text: str
    start_year: int
    end_year: int
    years: list[Year]
    role: str
    norm_baas: str

    def __repr__(self):
        return f"Domain(id={self.id}, name={self.name}, range={self.range_text}, years_count={len(self.years)})"


@dataclass(eq=False)
class SuperDomain:
    super_id: int
    name: str
    title: str
    domains: list[Domain]

    def __repr__(self):
        return f"SuperDomain(id={self.super_id}, name={self.name}, title={self.title}, domains_count={len(self.domains)})"


@dataclass(eq=False)
class Connection:
    from_year: int
    to_year: int
    name: str
    type: str

    def __repr__(self):
        return f"Connection(from={self.from_year}, to={self.to_year}, name={self.name}, type={self.type})"


@dataclass(eq=False)
class Container:
    title: str
    superdomains: list[SuperDomain]
    connections: list[Connection]

    def __repr__(self):
        return f"Container(title={self.title}, superdomains_count={len(self.superdomains)}, connections_count={len(self.connections)})"


def load_from_json(infrastructure_path: str, container_path: str) -> Container:
    """
    Lee infrastructure.json y container.json, construye la jerarquía de modelos
    y consolida todas las conexiones lógicas a nivel global de Container.
    """
    # 1. Leer el título del contenedor
    container_title = "Contenedor Desconocido"
    if os.path.exists(container_path):
        try:
            with open(container_path, 'r', encoding='utf-8') as f:
                c_data = json.load(f)
                if isinstance(c_data, list) and len(c_data) > 0:
                    container_title = c_data[0].get("title_container", "Sin Título")
        except Exception:
            pass

    # 2. Leer la jerarquía del archivo de infraestructura
    superdomains_list = []
    global_connections = []

    if os.path.exists(infrastructure_path):
        try:
            with open(infrastructure_path, 'r', encoding='utf-8') as f:
                infrastructure_data = json.load(f)
        except Exception:
            infrastructure_data = []

        for super_data in infrastructure_data:
            # Parsear datos de SuperDomain
            sd_name = super_data.get("superdomain", "")
            if not sd_name:
                continue

            sd_title = sd_name.replace("_", " ").title()
            sd_id = super_data.get("super_id", 0)

            # Parsear lista de dominios anidados
            domains_list = []
            for dom_data in super_data.get("domains", []):
                domain_name = dom_data.get("domain", "")
                range_text = dom_data.get("range", "")
                dom_id = dom_data.get("id", 0)

                # Calcular start_year y end_year
                try:
                    start_year, end_year = map(int, range_text.split("-"))
                except Exception:
                    start_year, end_year = 0, 0

                # Obtener rol y norm_baas
                role = dom_data.get("role", "")
                norm_baas = dom_data.get("norm_BaaS", dom_data.get("norm_baas", ""))

                # Crear el objeto Domain (inicialmente sin años para referenciarlo)
                domain_obj = Domain(
                    id=dom_id,
                    name=domain_name,
                    range_text=range_text,
                    start_year=start_year,
                    end_year=end_year,
                    years=[],
                    role=role,
                    norm_baas=norm_baas
                )

                # Instanciar objetos Year y asociarles la referencia al Domain padre
                years = []
                if start_year and end_year:
                    for y in range(start_year, end_year + 1):
                        years.append(Year(value=y, parent_domain=domain_obj))
                domain_obj.years = years

                domains_list.append(domain_obj)

            # Instanciar el SuperDomain
            sd_obj = SuperDomain(
                super_id=sd_id,
                name=sd_name,
                title=sd_title,
                domains=domains_list
            )
            superdomains_list.append(sd_obj)

            # Parsear y consolidar las conexiones anidadas del bloque a nivel global
            for conn_data in super_data.get("connections", []):
                from_year = conn_data.get("from", 0)
                to_year = conn_data.get("to", 0)
                name = conn_data.get("range_name", "")
                conn_type = conn_data.get("range_type", "")

                connection_obj = Connection(
                    from_year=from_year,
                    to_year=to_year,
                    name=name,
                    type=conn_type
                )
                global_connections.append(connection_obj)

    # Retornar el objeto raíz Container
    return Container(
        title=container_title,
        superdomains=superdomains_list,
        connections=global_connections
    )
