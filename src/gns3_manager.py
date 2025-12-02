from pathlib import Path
import re
from typing import Union, Dict

class Gns3Manager:
    # Initialiser le projet GNS3 et vérifier le répertoire Dynamips
    def __init__(self, project_path: Union[str, Path]) -> None:
        self.__project_path = Path(project_path)
        self.__dynamips_path = self.__project_path / "project-files" / "dynamips"
        if not self.__dynamips_path.exists():
            raise ValueError(f"Dynamips path does not exist: {self.__dynamips_path}")

    # Écrire les configs de démarrage pour chaque routeur
    def write_router_config(self, router_configs: Dict[str, str]) -> None:
        # Valider l'entrée
        if not isinstance(router_configs, dict):
            raise TypeError("router_configs must be a dict")

        # Vérifier que tous les routeurs existent
        existing = self.__get_existing_router_configs()
        missing = set(router_configs) - existing.keys()
        if missing:
            raise ValueError(f"Missing routers: {', '.join(missing)}")

        # Écrire chaque configuration
        for host, cfg in router_configs.items():
            try:
                Path(existing[host]).write_text(cfg)
            except Exception as e:
                raise IOError(f"Failed to write config for {host}: {e}")

    # Récupérer tous les routeurs et leurs chemins de configuration
    def __get_existing_router_configs(self) -> Dict[str, str]:
        configs: Dict[str, str] = {}
        for router_dir in self.__dynamips_path.iterdir():
            # Vérifier le répertoire configs
            if not router_dir.is_dir():
                continue
            cfg_dir = router_dir / "configs"
            if not cfg_dir.exists():
                raise ValueError(f"Missing 'configs' directory in {router_dir}")

            # Chercher le fichier de configuration unique
            files = list(cfg_dir.glob("*_startup-config.cfg"))
            if len(files) != 1:
                raise ValueError(f"Expected 1 cfg in {cfg_dir}, found {len(files)}")

            # Extraire l'hostname du fichier
            cfg_file = files[0]
            hostname = self.__extract_hostname(cfg_file)
            if not hostname:
                raise ValueError(f"No hostname found in {cfg_file}")

            configs[hostname] = str(cfg_file)

        if not configs:
            raise ValueError(f"No router configs found in {self.__dynamips_path}")

        return configs

    # Extraire le hostname du fichier de configuration
    def __extract_hostname(self, path: Path) -> Union[str, None]:
        try:
            for line in path.read_text().splitlines():
                match = re.match(r"^hostname\s+(\S+)", line, re.IGNORECASE)
                if match:
                    return match.group(1)
        except Exception as e:
            raise IOError(f"Error reading {path}: {e}")
        return None
