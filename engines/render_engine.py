# domain_visor/render_engine.py

from engines.models import load_from_json
from engines.layout_engine import LayoutEngine
from domain_visor.color_resolver import ColorResolver
from domain_visor.port_registry import PortRegistry
from engines.connection_engine import ConnectionEngine
from domain_visor.superdomain_item import SuperDomainItem
from domain_visor.domain_item import DomainItem
from year_visor.year_item import YearItem
from domain_visor.container_name_item import ContainerNameItem

class RenderEngine:
    """
    Coordinador de renderizado puro (JSON -> Models -> GraphicsItems -> Scene).
    Delega el cálculo de diseño al LayoutEngine, la resolución de color al ColorResolver,
    la resolución de puertos lógicos/visuales al PortRegistry y la creación de cables al ConnectionEngine.
    """
    def __init__(self, char_manager=None):
        self.layout_engine = LayoutEngine(char_manager)
        self.connection_engine = ConnectionEngine()

    def render(self, scene, container_path, domains_path):
        """
        Limpia la escena, carga el modelo jerárquico, obtiene la geometría de LayoutEngine,
        resuelve colores y puertos, e instancia todos los gráficos de forma dinámica delegando
        la resolución de cables al ConnectionEngine.
        """
        # 1. Limpiar escena e instanciar registro de puertos desacoplado
        scene.clear()
        registry = PortRegistry()

        # 2. Cargar el modelo jerárquico unificado
        container = load_from_json(domains_path, container_path)
        
        print(container)

        # 3. Obtener geometría espacial del LayoutEngine (Geometry -> GraphicsItems -> Scene)
        layout_data = self.layout_engine.calculate_layout(container)

        domain_items_map = {}

        # 4.0. Instanciar ContainerNameItem (etiqueta del nombre de la infraestructura)
        if "container_title" in layout_data:
            cx, cy, cw, ch = layout_data["container_title"]
            title_item = ContainerNameItem(cx, cy, cw, ch, container.title, container_path)
            scene.addItem(title_item)

        # 4.1. Instanciar SuperDomainItems
        for sd, geom in layout_data["superdomains"].items():
            x, y, w, h = geom
            sd_item = SuperDomainItem(x, y, w, h, sd.title)
            scene.addItem(sd_item)

        # 4.2. Instanciar DomainItems resolviendo sus colores con ColorResolver
        for domain, geom in layout_data["domains"].items():
            x, y, w, h = geom
            bg_color, border_color = ColorResolver.resolve_colors(domain.role)

            dom_item = DomainItem(
                x=x,
                y=y,
                width=w,
                height=h,
                title=domain.name,
                background_color=bg_color,
                border_color=border_color,
                domain_id=domain.id,
                infrastructure_path=domains_path
            )
            scene.addItem(dom_item)
            domain_items_map[domain] = dom_item

        # 4.3. Instanciar YearItems y registrar sus puertos en PortRegistry
        for year, geom in layout_data["years"].items():
            x, y, w, h = geom
            parent_domain = year.parent_domain
            dom_item = domain_items_map.get(parent_domain)

            y_item = YearItem(
                x=x,
                y=y,
                width=w,
                height=h,
                year_value=year.value,
                parent=dom_item
            )

            # Registrar puertos del año en el registro desacoplado
            registry.register_port(year.value, "left", y_item.left_port)
            registry.register_port(year.value, "right", y_item.right_port)

        # 5. Renderizar cables delegando la resolución y dibujo al ConnectionEngine (Commit 10)
        self.connection_engine.create_connections(scene, container, registry, domains_path)

        # 6. Configurar el tamaño del lienzo de la escena
        sx, sy, sw, sh = layout_data["scene_rect"]
        scene.setSceneRect(sx, sy, sw, sh)
