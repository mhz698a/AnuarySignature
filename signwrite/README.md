# SingEtude integrado

SingEtude se integra como un paquete interno de DomainViewer en esta carpeta.

- `signature_wm.py`: ventana no modal para redactar y guardar notas.
- `signature_dlg.py`: gestores de contactos y clasificaciones.
- `years_selector.py` y `utils.py`: selector de años y utilidades.
- `const.py`: constantes y rutas compartidas.
- `service.py`: ciclo de vida de la ventana, acciones de bandeja y apertura de la última nota.

Las bases de datos de contactos y clasificaciones se comparten desde `../__structure__/`. Las ventanas y cuadros de diálogo usan `../assets/directorio.ico`, el icono de DomainViewer. El destino de las notas se obtiene de la ruta dependiente configurada en DomainViewer.
