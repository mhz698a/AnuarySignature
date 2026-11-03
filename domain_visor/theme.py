# domain_visor/theme.py

class Theme:
    """
    Clase centralizada para definir todas las constantes visuales del visor de dominios.
    Toda constante de color, borde o estilo gráfico del sistema debe salir de aquí.
    """
    # Colores generales de la aplicación
    APP_BACKGROUND = "#1e1e1e"
    DOMAIN_VIEW_BACKGROUND = "#141414"
    TEXT_WHITE = "#ffffff"

    # SuperDomainItem
    SUPERDOMAIN_BG = "#2d2d2d"
    SUPERDOMAIN_BORDER = "#444444"

    # DomainItem y Roles (usados por ColorResolver)
    ROLE_EXODOMAIN_BG = "#2b73d6"        # Azul (exodomain_aurora_maya)
    ROLE_DEUTERODOMAIN_BG = "#b93a82"    # Rosa/Magenta (deuterodomain_alejandra_maya)
    ROLE_DEFAULT_BG = "#7c3ab9"          # Morado (por defecto)
    DOMAIN_BORDER = "#ffffff"

    # PortItem
    PORT_BORDER = "#ffffff"

    # CableItem
    CABLE_COLOR = "#d0d0d0"
    CABLE_SPECIAL_COLOR = "#ffffff"
    CABLE_DEUTEROLAZO_COLOR = "#ff1493"  # Rosa fuerte
    CABLE_EXOLAZO_COLOR = "#00bfff"      # Azul celeste
    CABLE_SUPERCABLE_COLOR = "#8D40F8"
