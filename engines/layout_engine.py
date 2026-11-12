# domain_visor/layout_engine.py

from character_visor.character_manager import CharacterManager
from PyQt6.QtGui import QFont, QFontMetrics

class LayoutEngine:
    """
    Responsabilidad única de diseño y posicionamiento:
    Define constantes de espaciado y calcula la geometría exacta de todos los elementos visuales.

    El renderer ya no calcula posiciones; en su lugar, consume los resultados de esta clase.
    """
    def __init__(self, char_manager=None):
        # Constantes de márgenes y geometría del lienzo
        self.margin_left = 100.0
        self.margin_top = 80.0
        self.margin_right = 100.0
        self.margin_bottom = 100.0

        # Constantes de columnas de SuperDomain
        self.column_width = 200.0
        self.spacing_columns = 90.0  # Calibrado: incrementado de 20.0 a 40.0 para mayor separación
        self.column_height = 450.0  # Altura por defecto

        # Constantes de bloques de Domain y espaciado
        self.spacing_blocks = 20.0  # Calibrado: Incrementado de 15.0 a 20.0 como estándar
        self.spacing_special = 40.0 # Calibrado: 40px para cruces especiales de cables
        self.header_height = 28.0

        # Constantes de YearItem
        self.year_base_height = 15.0
        self.year_character_row_top_gap = 4.0
        self.year_character_row_height = 20.0
        self.year_character_bottom_padding = 6.0
        self.year_top_padding = 8.0
        self.year_spacing = 4.0
        self.year_margin_sides = 8.0

        # Instancia de CharacterManager para calcular geometrías dinámicas
        self.char_manager = char_manager if char_manager is not None else CharacterManager()

    def get_year_height(self, year_value: int) -> float:
        """
        Calcula la altura dinámica del año.
        Si tiene perfiles/personajes, reserva el alto de la fila de iconos y un margen
        inferior de 6px respecto al borde que delimita el año.
        Si no, conserva el tamaño base de 15.0px.
        """
        characters = self.char_manager.get_characters_for_year(year_value)
        if characters:
            return (
                self.year_base_height
                + self.year_character_row_top_gap
                + self.year_character_row_height
                + self.year_character_bottom_padding
            )
        return self.year_base_height

    def _get_spacing_after_domain(self, domain_upper, domain_lower, connections):
        """
        Determina dinámicamente el espaciado entre dos dominios contiguos de la misma columna.
        Si existe una conexión entre el último año de domain_upper y el primer año de domain_lower,
        se retorna self.spacing_special (40px). De lo contrario, self.spacing_blocks (20px).
        """
        if not domain_upper.years or not domain_lower.years:
            return self.spacing_blocks
        u_last = domain_upper.years[-1].value
        l_first = domain_lower.years[0].value
        for conn in connections:
            if (conn.from_year == u_last and conn.to_year == l_first) or (conn.from_year == l_first and conn.to_year == u_last):
                return self.spacing_special
        return self.spacing_blocks

    def calculate_layout(self, container):
        """
        Calcula la geometría (x, y, ancho, alto) para cada SuperDomain, Domain y Year.

        Retorna un diccionario estructurado:
            {
                "superdomains": {sd_obj: (x, y, w, h)},
                "domains": {domain_obj: (x, y, w, h)},
                "years": {year_obj: (x, y, w, h)},
                "scene_rect": (x, y, w, h)
            }
        """
        # Paso de Calibración (Commit 12.1):
        # Primero, calculamos dinámicamente la altura necesaria para cada columna de SuperDomain,
        # previniendo desbordamientos (overflows) si hay muchos dominios o años en una columna.
        max_needed_height = self.column_height

        for sd in container.superdomains:
            # Espacio vertical inicial: 50px de espacio superior para el título de la columna
            col_height = 50.0
            for idx, domain in enumerate(sd.domains):
                # Altura correcta del dominio considerando: encabezado (28px) + padding superior (8px)
                # + (alturas dinámicas de los años) + (espaciado_entre_años) + padding inferior (8px)
                years_count = len(domain.years)
                years_total_height = 0.0
                if years_count > 0:
                    for yr in domain.years:
                        years_total_height += self.get_year_height(yr.value)
                    years_total_height += (years_count - 1) * self.year_spacing

                domain_height = self.header_height + self.year_top_padding + years_total_height + self.year_top_padding
                
                if idx < len(sd.domains) - 1:
                    spacing = self._get_spacing_after_domain(domain, sd.domains[idx+1], container.connections)
                else:
                    spacing = self.spacing_blocks
                col_height += domain_height + spacing
            
            # Dejamos un margen inferior de padding al final de la columna
            col_height += 15.0
            if col_height > max_needed_height:
                max_needed_height = col_height

        # Asignamos la altura de columna calculada dinámicamente
        active_column_height = max_needed_height

        superdomains_geom = {}
        domains_geom = {}
        years_geom = {}

        for i, sd in enumerate(container.superdomains):
            sd_x = self.margin_left + i * (self.column_width + self.spacing_columns)
            sd_y = self.margin_top
            superdomains_geom[sd] = (sd_x, sd_y, self.column_width, active_column_height)

            # Posicionar secuencialmente los DomainItems dentro de este contenedor de columna
            # Se deja un espacio vertical de 50px para el encabezado del SuperDomainItem
            current_y = sd_y + 50.0

            for idx, domain in enumerate(sd.domains):
                # Altura calibrada del bloque de dominio
                years_count = len(domain.years)
                years_total_height = 0.0
                if years_count > 0:
                    for yr in domain.years:
                        years_total_height += self.get_year_height(yr.value)
                    years_total_height += (years_count - 1) * self.year_spacing

                domain_height = self.header_height + self.year_top_padding + years_total_height + self.year_top_padding

                dom_x = sd_x + 10.0
                dom_y = current_y
                dom_width = self.column_width - 20.0
                domains_geom[domain] = (dom_x, dom_y, dom_width, domain_height)

                # Posicionar YearItems con márgenes a los lados y espaciado vertical dinámico
                year_start_y = dom_y + self.header_height + self.year_top_padding
                current_year_y = year_start_y

                for idx_year, year in enumerate(domain.years):
                    y_height = self.get_year_height(year.value)
                    y_x = dom_x + self.year_margin_sides
                    y_width = dom_width - (2.0 * self.year_margin_sides)
                    years_geom[year] = (y_x, current_year_y, y_width, y_height)

                    # Avanzar para el siguiente año
                    current_year_y += y_height + self.year_spacing

                if idx < len(sd.domains) - 1:
                    spacing = self._get_spacing_after_domain(domain, sd.domains[idx+1], container.connections)
                else:
                    spacing = self.spacing_blocks

                # Avanzar la coordenada Y para el siguiente bloque de dominio más el espacio entre bloques
                current_y += domain_height + spacing

        # Dimensiones totales de la escena para el bounding box
        if container.superdomains:
            last_sd_right = self.margin_left + (len(container.superdomains) - 1) * (self.column_width + self.spacing_columns) + self.column_width
            total_width = last_sd_right + self.margin_right
        else:
            total_width = self.margin_left + self.margin_right

        total_height = self.margin_top + active_column_height + self.margin_bottom
        scene_rect = (0.0, 0.0, float(total_width), float(total_height))

        # Calcular dimensiones y posición del título del contenedor (container_title_item)
        title_str = getattr(container, "title", "")
        try:
            
            font = QFont("Arial", 11, QFont.Weight.Bold)
            fm = QFontMetrics(font)
            title_w = max(120.0, float(fm.horizontalAdvance(title_str) + 20))
            title_h = max(28.0, float(fm.height() + 10))
        except Exception:
            title_w = max(120.0, float(len(title_str) * 9 + 20))
            title_h = 30.0

        title_x = (total_width - title_w) / 2.0
        title_y = 20.0

        return {
            "container_title": (title_x, title_y, title_w, title_h),
            "superdomains": superdomains_geom,
            "domains": domains_geom,
            "years": years_geom,
            "scene_rect": scene_rect
        }
