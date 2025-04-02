from pathlib import Path
import re


class Gns3Project:
    def __init__(self, project_path):
        """
        Initializes the parser with the absolute path of the GNS3 project.
        """
        self.project_path = Path(project_path)
        self.dynamips_path = self.project_path / "project-files" / "dynamips"

        if not self.dynamips_path.exists():
            raise ValueError(f"Dynamips path does not exist: {self.dynamips_path}")

    def write_router_config(self, router_configs):
        """
        Writes configuration texts to the respective router configuration files.
        """
        if not isinstance(router_configs, dict):
            raise TypeError("router_configs must be a dictionary")

        existing_configs = self._get_existing_router_configs()

        # Identify missing routers
        missing_routers = [hostname for hostname in router_configs if hostname not in existing_configs]

        if missing_routers:
            missing_list = ", ".join(missing_routers)
            raise ValueError(f"The following routers are missing in the project: {missing_list}")

        # All routers exist; proceed to write configurations
        for hostname, config_text in router_configs.items():
            config_file_path = Path(existing_configs[hostname])

            try:
                with config_file_path.open("w") as config_file:
                    config_file.write(config_text)
            except Exception as e:
                raise IOError(f"Failed to write configuration for '{hostname}' to {config_file_path}: {e}")

    def _get_existing_router_configs(self):
        """
        Retrieves existing router configurations by extracting hostnames from config files.
        """
        router_configs = {}

        # Iterate over each router folder in Dynamips
        for router_folder in self.dynamips_path.iterdir():
            if router_folder.is_dir():
                configs_dir = router_folder / "configs"

                if not configs_dir.exists():
                    raise ValueError(f"'configs' directory not found in {router_folder}")

                # Find the single file matching the pattern *_startup-config.cfg
                config_files = list(configs_dir.glob("*_startup-config.cfg"))

                if len(config_files) != 1:
                    raise ValueError(
                        f"Expected exactly one startup-config.cfg file in {configs_dir}, found {len(config_files)}"
                    )

                # Extract hostname
                config_file = config_files[0]
                hostname = self._extract_hostname(config_file)

                if not hostname:
                    raise ValueError(f"Hostname not found in {config_file}")

                router_configs[hostname] = str(config_file)

        if not router_configs:
            raise ValueError(f"No router configurations found in {self.dynamips_path}")

        return router_configs

    @staticmethod
    def _extract_hostname(config_file_path):
        """
        Extracts the hostname from a configuration file.
        """
        try:
            with config_file_path.open("r") as file:
                for line in file:
                    line = line.strip()
                    # Use regex to find the line starting with 'hostname'
                    match = re.match(r'^hostname\s+(\S+)', line, re.IGNORECASE)
                    if match:
                        return match.group(1)
        except Exception as e:
            raise IOError(f"Error reading {config_file_path}: {e}")

        return None
