# domain_visor/character_manager.py

import os
import json
import datetime
from pathlib import Path

class CharacterManager:
    """
    Gestiona la carga dinámica y cacheada de perfiles/personajes.
    - Escanea directorios de años desde el primer año de la infraestructura hasta el año actual.
    - Valida carpetas de personajes que tengan exactamente 4 puntos y comas (';').
    - Crea y lee archivos JSON de personaje con el nombre __{name}__.json.
    - Guarda y consulta un archivo cache global en __structure__/characters_cache.json.
    """
    TRUST_CACHE = False  # Bandera constante en el código

    def __init__(self, base_path=None, cache_path=None, infrastructure_path=None):
        # Permitir sobreescribir rutas para testing
        self.base_path = Path(base_path) if base_path else Path("E:/_Internal")
        self.cache_path = Path(cache_path) if cache_path else Path("__structure__/characters_cache.json")
        self.infrastructure_path = Path(infrastructure_path) if infrastructure_path else Path("__structure__/infrastructure.json")
        self._cache = {}
        self.load_cache_file()

    def get_first_infrastructure_year(self) -> int:
        """
        Lee infrastructure.json y retorna el año mínimo de inicio de los dominios.
        Si no se puede leer, retorna 1999 por defecto.
        """
        if not self.infrastructure_path.exists():
            return 1999
        try:
            with open(self.infrastructure_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            min_year = None
            for sd in data:
                for domain in sd.get("domains", []):
                    range_text = domain.get("range", "")
                    if "-" in range_text:
                        try:
                            start_year = int(range_text.split("-")[0])
                            if min_year is None or start_year < min_year:
                                min_year = start_year
                        except ValueError:
                            pass
            return min_year if min_year is not None else 1999
        except Exception:
            return 1999

    def load_cache_file(self):
        """Carga el archivo de caché si existe."""
        if self.cache_path.exists():
            try:
                with open(self.cache_path, "r", encoding="utf-8") as f:
                    self._cache = json.load(f)
            except Exception:
                self._cache = {}
        else:
            self._cache = {}

    def save_cache_file(self):
        """Guarda la caché actual al archivo JSON."""
        try:
            self.cache_path.parent.mkdir(parents=True, exist_ok=True)
            with open(self.cache_path, "w", encoding="utf-8") as f:
                json.dump(self._cache, f, indent=2, ensure_ascii=False)
        except Exception as e:
            print(f"Error guardando caché de personajes: {e}")

    @staticmethod
    def _find_character_json_file(character_dir: Path, character_name: str = ""):
        """Localiza la credencial JSON existente dentro de la carpeta del personaje."""
        expected_json = character_dir / f"__{character_name}__.json" if character_name else None
        if expected_json and expected_json.is_file():
            return expected_json

        json_files = sorted(path for path in character_dir.glob("__*.json") if path.is_file())
        return json_files[0] if json_files else None

    @classmethod
    def _resolve_cached_json_path(cls, char_data: dict):
        """Resuelve character_json_path, migrando temporalmente cachés antiguas."""
        json_path_str = char_data.get("character_json_path", "")
        if json_path_str:
            json_path = Path(json_path_str)
            if json_path.is_file():
                return json_path

        # Compatibilidad con cachés antiguas que todavía guardan character_path.
        legacy_dir_str = char_data.get("character_path", "")
        if legacy_dir_str:
            legacy_dir = Path(legacy_dir_str)
            if legacy_dir.is_dir():
                return cls._find_character_json_file(legacy_dir, char_data.get("name", ""))

        return None

    def migrate_cached_characters(self):
        """Migra la caché antigua a rutas de credencial y elimina character_path."""
        dirty = False
        for year_str, characters in list(self._cache.items()):
            valid_characters = []
            for char_data in characters:
                json_path = self._resolve_cached_json_path(char_data)
                if json_path:
                    normalized_path = str(json_path.resolve())
                    if char_data.get("character_json_path") != normalized_path:
                        char_data["character_json_path"] = normalized_path
                        dirty = True
                    valid_characters.append(char_data)
                else:
                    dirty = True

                if "character_path" in char_data:
                    char_data.pop("character_path", None)
                    dirty = True

            if len(valid_characters) != len(characters):
                self._cache[year_str] = valid_characters
                dirty = True

        if dirty:
            self.save_cache_file()

    @staticmethod
    def _credential_payload(char_data: dict) -> dict:
        """Construye el JSON persistido sin los metadatos incluidos en la carpeta."""
        credential_data = char_data.copy()
        for deprecated_field in ("position", "birthday", "age"):
            credential_data.pop(deprecated_field, None)
        credential_data.setdefault("secondary_color", "")
        return {"character_data": credential_data}

    @staticmethod
    def _find_first_image(character_dir: Path) -> str:
        image_extensions = {".png", ".jpg", ".jpeg", ".webp", ".gif", ".bmp"}
        for sub_item in sorted(character_dir.iterdir()):
            if sub_item.is_file() and sub_item.suffix.lower() in image_extensions:
                return sub_item.name
        return ""

    def verify_cache_at_startup(self):
        """Migra la caché antigua y vuelve a indexar las credenciales disponibles."""
        self.migrate_cached_characters()
        self.scan_all_years()

    def scan_all_years(self, progress_callback=None):
        """
        Escanea las carpetas de años desde el primer año hasta el año actual.
        Filtra años futuros. Actualiza la caché con los personajes encontrados.
        """
        # Migrar las referencias antiguas antes de iniciar el escaneo.
        self.migrate_cached_characters()

        # 1. Comprobar si la ruta base existe. Si no, mostramos un mensaje por consola
        # pero permitimos que la caché de credenciales ya localizadas pueda seguir utilizándose.
        if not self.base_path.exists():
            print(f"Advertencia: La ruta base {self.base_path} no existe. No se cargarán nuevos personajes de disco.")
            return

        first_year = self.get_first_infrastructure_year()
        current_year = datetime.date.today().year

        updated_cache = {}

        total_years = max(1, current_year - first_year + 1)
        for year_index, year in enumerate(range(first_year, current_year + 1), start=1):
            album_prefix = f"{max(0, year - 2003):02d}"
            year_dir = self.base_path / str(year) / f"{album_prefix}. album"

            if not year_dir.exists():
                if progress_callback:
                    progress_callback(year_index, total_years, year)
                continue

            characters_list = []
            try:
                # Listar subcarpetas dentro de year_dir
                for item in year_dir.iterdir():
                    if item.is_dir():
                        folder_name = item.name
                        # Debe cumplir con tener el prefijo y contener exactamente 4 ';'
                        prefix_to_check = f"{album_prefix}. "
                        if not folder_name.startswith(prefix_to_check):
                            continue

                        rest = folder_name[len(prefix_to_check):]
                        if rest.count(";") != 4:
                            continue

                        # Separar los 5 componentes
                        parts = rest.split(";")
                        raw_pos, alterego, name, birthday, raw_age = parts

                        try:
                            position = int(raw_pos)
                            age = int(raw_age)
                            # Validar formato de birthday yyyy-mm-dd de forma básica
                            datetime.datetime.strptime(birthday, "%Y-%m-%d")
                        except ValueError:
                            # Si la posición, edad o la fecha no son válidas, descartamos
                            continue

                        target_json = item / f"__{name}__.json"
                        found_json_file = None
                        char_data = {}

                        # Buscar si existe el archivo con el nuevo nombre o algún archivo __*.json anterior
                        if target_json.exists():
                            found_json_file = target_json
                        else:
                            for sub_file in item.glob("__*.json"):
                                if sub_file.is_file():
                                    found_json_file = sub_file
                                    break

                        if found_json_file and found_json_file.exists():
                            try:
                                with open(found_json_file, "r", encoding="utf-8") as jf:
                                    loaded_data = json.load(jf)
                                    char_data = loaded_data.get("character_data", {})
                            except Exception:
                                pass

                        if char_data:
                            # Sincronizar campos de credencial con el nombre actual de la carpeta
                            char_data["year"] = year
                            char_data["position"] = position
                            # Mantener los nombres editables de la credencial. La carpeta
                            # conserva su nombre histórico y solo aporta fallbacks iniciales.
                            if not char_data.get("name"):
                                char_data["name"] = name
                            if not char_data.get("alterego"):
                                char_data["alterego"] = alterego
                            char_data["birthday"] = birthday
                            char_data["age"] = age
                            # Conservar el archivo JSON que ya existe dentro de la carpeta.
                            credential_json_file = found_json_file or target_json
                            char_data.pop("character_path", None)
                            char_data["character_json_path"] = str(credential_json_file.resolve())

                            # Si la ruta de imagen guardada dejó de existir, recuperar una imagen local.
                            icon_path = str(char_data.get("icon_path", "")).strip()
                            if icon_path:
                                icon_file = Path(icon_path)
                                resolved_icon = icon_file if icon_file.is_absolute() else item / icon_file
                                if not resolved_icon.is_file():
                                    char_data["icon_path"] = self._find_first_image(item)
                            else:
                                char_data["icon_path"] = self._find_first_image(item)

                            char_data.setdefault("secondary_color", "")

                            # Guardar en el mismo archivo de credencial detectado.
                            try:
                                with open(credential_json_file, "w", encoding="utf-8") as jf:
                                    json.dump(self._credential_payload(char_data), jf, indent=4, ensure_ascii=False)
                            except Exception as e:
                                print(f"Error guardando JSON sincronizado en personaje: {e}")

                        else:
                            # Buscar la primera imagen disponible en la carpeta del personaje.
                            icon_path = self._find_first_image(item)

                            char_data = {
                                "year": year,
                                "position": position,
                                "name": name,
                                "alterego": alterego,
                                "birthday": birthday,
                                "age": age,
                                "icon_path": icon_path,
                                "background_path": "",
                                "type_underwear": [],
                                "short_masked_alterego": "",
                                "character_json_path": str(target_json.resolve()),
                                "color_group": "",
                                "secondary_color": "",
                                "profession_group": "",
                                "time_of_year": ""
                            }

                            # Guardar el JSON en la carpeta
                            try:
                                with open(target_json, "w", encoding="utf-8") as jf:
                                    json.dump(self._credential_payload(char_data), jf, indent=4, ensure_ascii=False)
                            except Exception as e:
                                print(f"Error guardando JSON en personaje: {e}")

                        char_data.setdefault("secondary_color", "")

                        # Agregar a la lista para guardar en caché
                        characters_list.append(char_data)
            except Exception as e:
                print(f"Error procesando el año {year}: {e}")

            if characters_list:
                # Almacenar en caché ordenados por posición y luego por nombre alfabéticamente
                characters_list.sort(key=lambda c: (c.get("position", 0), c.get("name", "").lower()))
                # Limitar a un máximo de 6 perfiles por año (requisito profiles_row_item tiene capacidad de mostrar 6 perfiles)
                updated_cache[str(year)] = characters_list[:6]

            if progress_callback:
                progress_callback(year_index, total_years, year)

        # Actualizar la caché en memoria y guardarla en el archivo
        self._cache.update(updated_cache)
        self.save_cache_file()

    def get_characters_for_year(self, year: int) -> list:
        """
        Retorna la lista de personajes (hasta 6) para un año determinado usando la caché.
        """
        return self._cache.get(str(year), [])
