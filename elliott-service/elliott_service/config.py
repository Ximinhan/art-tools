import os
from dataclasses import dataclass


@dataclass
class Settings:
    api_token: str = ""
    elliott_data_path: str = "https://github.com/openshift-eng/ocp-build-data"
    elliott_working_dir: str = "/tmp/elliott-work"
    default_timeout: int = 120

    @classmethod
    def from_env(cls) -> "Settings":
        return cls(
            api_token=os.environ.get("ELLIOTT_API_TOKEN", ""),
            elliott_data_path=os.environ.get(
                "ELLIOTT_DATA_PATH",
                "https://github.com/openshift-eng/ocp-build-data",
            ),
            elliott_working_dir=os.environ.get("ELLIOTT_WORKING_DIR", "/tmp/elliott-work"),
            default_timeout=int(os.environ.get("ELLIOTT_DEFAULT_TIMEOUT", "120")),
        )


settings = Settings.from_env()
