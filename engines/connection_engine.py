# domain_visor/connection_engine.py

from domain_visor.cable_item import CableItem

class ConnectionEngine:
    """
    Responsabilidad única:
    Conectar puertos lógicos resolviendo referencias mediante PortRegistry y crear CableItems en la escena.

    No conoce los archivos JSON ni carga datos. Solo consume Connections ya cargadas y puertos registrados.
    """
    def __init__(self):
        pass

    def create_connections(self, scene, container, registry, domains_path=None):
        """
        Itera sobre una lista de objetos Connection en el container, obtiene sus puertos (derecho e izquierdo)
        desde PortRegistry, crea los objetos gráficos CableItem correspondientes y los agrega a la escena.
        """
        # Build logical map of year_value -> (Domain, SuperDomain, index_of_domain)
        year_to_logical = {}
        for sd in container.superdomains:
            for d_idx, domain in enumerate(sd.domains):
                for year in domain.years:
                    year_to_logical[year.value] = (domain, sd, d_idx)

        for connection in container.connections:
            # Obtener puertos izquierdo y derecho de ambos extremos
            left_from = registry.get_port(connection.from_year, "left")
            right_from = registry.get_port(connection.from_year, "right")
            left_to = registry.get_port(connection.to_year, "left")
            right_to = registry.get_port(connection.to_year, "right")

            if left_from and left_to:
                # Check if it is a special last-to-first connection in the same column
                is_special = False
                info_from = year_to_logical.get(connection.from_year)
                info_to = year_to_logical.get(connection.to_year)

                if info_from and info_to:
                    dom_from, sd_from, idx_from = info_from
                    dom_to, sd_to, idx_to = info_to

                    if sd_from == sd_to:
                        if idx_from + 1 == idx_to:
                            if connection.from_year == dom_from.years[-1].value and connection.to_year == dom_to.years[0].value:
                                is_special = True
                        elif idx_to + 1 == idx_from:
                            if connection.to_year == dom_to.years[-1].value and connection.from_year == dom_from.years[0].value:
                                is_special = True

                if is_special:
                    if idx_from + 1 == idx_to:
                        from_port = right_from
                        to_port = left_to
                    else:
                        from_port = left_from
                        to_port = right_to
                else:
                    # Determinar de forma inteligente los lados de conexión según el flujo horizontal (Calibrado: Commit 12.1):
                    # - Si el origen está más a la izquierda que el destino (flujo de izquierda a derecha),
                    #   conectamos el puerto derecho del origen al puerto izquierdo del destino.
                    # - Si el origen está más a la derecha que el destino (flujo de derecha a izquierda),
                    #   conectamos el puerto izquierdo del origen al puerto derecho del destino.
                    # - Si están en la misma columna, conectamos del puerto derecho al derecho de ambos años.
                    if left_from._x < left_to._x:
                        from_port = right_from
                        to_port = left_to
                    elif left_from._x > left_to._x:
                        from_port = left_from
                        to_port = right_to
                    else:
                        from_port = right_from
                        to_port = right_to

                if from_port and to_port:
                    cable = CableItem(from_port, to_port, connection, is_special=is_special, json_path=domains_path)
                    scene.addItem(cable)
            else:
                # Respaldo clásico si no se encuentran ambos lados
                from_port = registry.get_port(connection.from_year, "right")
                to_port = registry.get_port(connection.to_year, "left")
                if from_port and to_port:
                    cable = CableItem(from_port, to_port, connection, json_path=domains_path)
                    scene.addItem(cable)
