"""BioYoda substrate server configuration (env-overridable, sensible defaults)."""
import os
from dataclasses import dataclass
from pathlib import Path

DEFAULT_LOG_DIR = Path(__file__).parent.parent / "logs"


@dataclass
class Config:
    qdrant_url: str = "http://localhost:6333"
    host: str = "0.0.0.0"
    port: int = 8011                      # avoids :8000 (biobtree MCP) and :9291 (biobtree core)
    log_level: str = "INFO"
    log_dir: Path = DEFAULT_LOG_DIR
    log_requests: bool = True
    mcp_server_name: str = "bioyoda"

    @classmethod
    def from_env(cls):
        d = os.getenv("BIOYODA_LOG_DIR")
        return cls(
            qdrant_url=os.getenv("BIOYODA_QDRANT_URL", "http://localhost:6333"),
            host=os.getenv("BIOYODA_HOST", "0.0.0.0"),
            port=int(os.getenv("BIOYODA_PORT", "8011")),
            log_level=os.getenv("BIOYODA_LOG_LEVEL", "INFO").upper(),
            log_dir=Path(d) if d else DEFAULT_LOG_DIR,
            log_requests=os.getenv("BIOYODA_LOG_REQUESTS", "true").lower() == "true",
            mcp_server_name=os.getenv("BIOYODA_MCP_NAME", "bioyoda"),
        )

    @property
    def log_file(self): return self.log_dir / "bioyoda_server.log"
    @property
    def access_log_file(self): return self.log_dir / "bioyoda_access.log"


config = Config.from_env()
