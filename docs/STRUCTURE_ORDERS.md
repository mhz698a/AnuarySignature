# Órdenes de Structure

Las órdenes viven en el repositorio privado AnuarySignature-Structure bajo:

```text
__structure__/orders/pending/<order-id>.json
```

La IA puede proponer una orden creando ese archivo mediante una rama y un Pull
Request en el repositorio privado. La orden no se ejecuta al crearse ni al
descargarse. Después de revisar y fusionar el Pull Request, el usuario descarga
los cambios desde AnuarySignature y abre:

**Herramientas → Revisar órdenes de GitHub**

Cada orden requiere una segunda aprobación explícita dentro de la aplicación.

## Esquema

Cada archivo contiene una sola operación:

```json
{
  "schema_version": 1,
  "id": "order-2026-11-001",
  "title": "Actualizar colores de Emiru",
  "description": "Completar los colores temáticos investigados.",
  "created_at": "2026-11-21T12:00:00-06:00",
  "expires_at": null,
  "operation": {
    "type": "update_character_credential",
    "target": {
      "year": 2018,
      "name": "emiru_aisaki",
      "alterego": "cure_machérie"
    },
    "fields": {
      "color_group": "rojo",
      "secondary_color": "rosa"
    }
  }
}
```

El identificador debe tener entre 8 y 80 caracteres alfanuméricos, guion o
guion bajo. Se utiliza una orden por archivo para que cada cambio tenga una
vista previa y una aprobación independientes.

## Operaciones admitidas

### `update_character_credential`

Actualiza campos permitidos de una credencial existente, identificada por año,
nombre y alterego. Los campos admitidos son:

- `icon_path`, `background_path`
- `type_underwear`
- `short_masked_alterego`
- `color_group`, `secondary_color`
- `profession_group`, `time_of_year`

Los cambios de ruta de imagen solo pueden referenciar imágenes que ya existan
dentro de la unidad dependiente. Esta operación no descarga ni copia imágenes.

### `replace_character_asset`

Copia una imagen incluida por la orden en `__structure__/orders/assets/` a la
carpeta del personaje y actualiza `icon_path` o `background_path`:

```json
{
  "type": "replace_character_asset",
  "target": {
    "year": 2018,
    "name": "emiru_aisaki",
    "alterego": "cure_machérie"
  },
  "field": "icon_path",
  "asset_path": "assets/emiru-new-icon.png"
}
```

La imagen nueva recibe un nombre asociado al identificador de orden. La imagen
anterior permanece en la unidad dependiente; no se elimina ni se mueve. Los
formatos admitidos son PNG, JPG, JPEG, WEBP, GIF y BMP, hasta 25 MB.

### `update_dependent_json`

Actualiza un JSON existente dentro de la unidad dependiente. Requiere:

```json
{
  "type": "update_dependent_json",
  "path": "2018/identity.json",
  "document": {
    "example": true
  }
}
```

Antes de reemplazar el documento se guarda una copia íntegra del JSON previo en
`%LOCALAPPDATA%\\AnuarySignature\\Backups\\DependentOrders`.

### `create_directory`

Crea un directorio dentro de la unidad dependiente si no existe:

```json
{
  "type": "create_directory",
  "path": "2018/15. new-folder"
}
```

No reemplaza carpetas existentes ni borra su contenido.

## Operaciones prohibidas

La versión actual rechaza expresamente órdenes de:

- Eliminar archivos o directorios.
- Mover o renombrar archivos o directorios.
- Ejecutar scripts, comandos de shell o código.
- Escribir fuera de la unidad dependiente configurada.
- Modificar archivos que no sean JSON mediante `update_dependent_json`.

No existe un tipo de orden de eliminación. Si una propuesta futura necesitara
borrar algo, primero se debe diseñar y revisar contigo la integración con la
Papelera de reciclaje de Windows. Nunca se añadirá una eliminación silenciosa.

## Flujo

1. La IA prepara un archivo de orden y abre un Pull Request en el repositorio
   privado Structure.
2. El usuario revisa y fusiona ese Pull Request.
3. AnuarySignature muestra PULL en la statusbar; el usuario descarga los cambios.
4. El usuario abre **Herramientas → Revisar órdenes de GitHub**.
5. La aplicación valida el esquema, la identidad del personaje, las rutas y el
   tipo de operación, y muestra una vista previa.
6. El usuario pulsa **Aplicar orden** y confirma.
7. Los archivos JSON existentes se respaldan antes de modificarse. El
   identificador se guarda localmente para no repetir la orden.
8. La aplicación crea un resultado en
   `__structure__/orders/results/<order-id>.json`. El usuario decide cuándo
   publicar ese resultado con **Subir cambios**.

Una orden aplicada permanece en `pending` en GitHub; su resultado permite
auditarla. La aplicación la excluye localmente para que no vuelva a ejecutarse
en ese equipo.
