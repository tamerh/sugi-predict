"""Configuration management for agent system."""

import os
from pathlib import Path
from typing import Any, Dict, Optional

import yaml
from pydantic import BaseModel, Field
from pydantic_settings import BaseSettings


class GrpcConfig(BaseModel):
    """gRPC connection configuration."""
    host: str = "scc2"
    port: int = 7777
    max_connections: int = 50
    keepalive_time: int = 30
    timeout: int = 30


class RestConfig(BaseModel):
    """REST connection configuration."""
    host: str = "scc2"
    port: int = 9292
    timeout: int = 30


class BioBTreeConfig(BaseModel):
    """BioBTree integration configuration."""
    protocol: str = "grpc"
    grpc: GrpcConfig = Field(default_factory=GrpcConfig)
    rest: RestConfig = Field(default_factory=RestConfig)
    retry_attempts: int = 3
    retry_delay: int = 1


class QdrantConfig(BaseModel):
    """Qdrant vector database configuration."""
    host: str = "localhost"
    port: int = 6333
    timeout: int = 10
    collections: Dict[str, str] = Field(default_factory=dict)


class RedisConfig(BaseModel):
    """Redis cache configuration."""
    host: str = "localhost"
    port: int = 6379
    db: int = 0
    cache_ttl_hours: int = 24
    enabled: bool = True


class IntegrationsConfig(BaseModel):
    """External integrations configuration."""
    biobtree: BioBTreeConfig = Field(default_factory=BioBTreeConfig)
    qdrant: QdrantConfig = Field(default_factory=QdrantConfig)
    redis: RedisConfig = Field(default_factory=RedisConfig)


class LLMProviderConfig(BaseModel):
    """Single LLM provider configuration."""
    model: Optional[str] = None
    api_key_env: Optional[str] = None
    max_tokens: int = 4096
    temperature: float = 0.0
    timeout: int = 60


class LLMConfig(BaseModel):
    """LLM providers configuration."""
    default_provider: Optional[str] = None  # Can be null to use main config
    providers: Dict[str, LLMProviderConfig] = Field(default_factory=dict)


class AgentConfig(BaseModel):
    """Agent execution configuration."""
    max_iterations: int = 5
    tool_timeout: int = 30
    reasoning_engine: Dict[str, Any] = Field(default_factory=dict)
    specialized: Dict[str, Any] = Field(default_factory=dict)


class PromptsConfig(BaseModel):
    """Prompts configuration."""
    directory: str = "modules/agent_system/prompts"
    cache_enabled: bool = True
    version: str = "v1"


class LoggingConfig(BaseModel):
    """Logging configuration."""
    level: str = "INFO"
    format: str = "json"
    handlers: Dict[str, Any] = Field(default_factory=dict)
    structured: Dict[str, bool] = Field(default_factory=dict)


class MonitoringConfig(BaseModel):
    """Monitoring configuration."""
    enabled: bool = True
    prometheus_port: int = 9090
    tracing_enabled: bool = False
    metrics: list[str] = Field(default_factory=list)


class DevelopmentConfig(BaseModel):
    """Development settings."""
    debug: bool = False
    reload: bool = False
    profile: bool = False


class AgentSystemConfig(BaseSettings):
    """Main configuration for agent system."""

    gateway: Dict[str, Any] = Field(default_factory=dict)
    integrations: IntegrationsConfig = Field(default_factory=IntegrationsConfig)
    llm: LLMConfig = Field(default_factory=LLMConfig)
    agents: AgentConfig = Field(default_factory=AgentConfig)
    prompts: PromptsConfig = Field(default_factory=PromptsConfig)
    logging: LoggingConfig = Field(default_factory=LoggingConfig)
    monitoring: MonitoringConfig = Field(default_factory=MonitoringConfig)
    development: DevelopmentConfig = Field(default_factory=DevelopmentConfig)

    class Config:
        env_prefix = "BIOYODA_"
        case_sensitive = False


def load_config(config_path: Optional[Path] = None, merge_main_config: bool = True) -> AgentSystemConfig:
    """
    Load configuration from YAML file with optional merge from main BioYoda config.

    Args:
        config_path: Path to config file. If None, uses default location.
        merge_main_config: If True, merge with config/config.yaml -> rag section for LLM settings

    Returns:
        Loaded configuration

    Raises:
        FileNotFoundError: If config file not found
        ValueError: If config is invalid
    """
    if config_path is None:
        # Default to config/agent_system.yaml
        repo_root = Path(__file__).parent.parent.parent.parent
        config_path = repo_root / "config" / "agent_system.yaml"

    if not config_path.exists():
        raise FileNotFoundError(f"Configuration file not found: {config_path}")

    # Load agent system config
    with open(config_path, 'r') as f:
        config_dict = yaml.safe_load(f)

    # Merge with main BioYoda config if requested
    if merge_main_config:
        repo_root = Path(__file__).parent.parent.parent.parent
        main_config_path = repo_root / "config" / "config.yaml"

        if main_config_path.exists():
            with open(main_config_path, 'r') as f:
                main_config = yaml.safe_load(f)

            # Merge RAG section into LLM config if not explicitly set
            if 'rag' in main_config:
                rag_config = main_config['rag']

                # Use RAG provider if LLM default_provider is null
                if config_dict.get('llm', {}).get('default_provider') is None:
                    if 'provider' in rag_config:
                        config_dict.setdefault('llm', {})
                        config_dict['llm']['default_provider'] = rag_config['provider']

                # Merge provider-specific settings
                if 'provider' in rag_config and 'model' in rag_config:
                    provider = rag_config['provider']
                    config_dict.setdefault('llm', {}).setdefault('providers', {})

                    # Update provider config if not already set
                    if provider not in config_dict['llm']['providers']:
                        config_dict['llm']['providers'][provider] = {}

                    provider_config = config_dict['llm']['providers'][provider]

                    # Merge model
                    if 'model' not in provider_config or provider_config['model'] is None:
                        provider_config['model'] = rag_config['model']

                    # Merge API key (handle both direct value and env var)
                    if 'api_key' in rag_config:
                        api_key = rag_config['api_key']
                        # Check if it's an environment variable reference
                        if isinstance(api_key, str) and not api_key.startswith('${'):
                            # Direct API key value - set it as environment variable
                            os.environ[f'{provider.upper()}_API_KEY'] = api_key

                    # Merge temperature
                    if 'default_temperature' in rag_config:
                        if 'temperature' not in provider_config:
                            provider_config['temperature'] = rag_config['default_temperature']

                    # Merge max_tokens
                    if 'default_max_tokens' in rag_config:
                        if 'max_tokens' not in provider_config:
                            provider_config['max_tokens'] = rag_config['default_max_tokens']

    # Create config object
    config = AgentSystemConfig(**config_dict)

    return config


# Global config instance (lazy loaded)
_config: Optional[AgentSystemConfig] = None


def get_config() -> AgentSystemConfig:
    """
    Get global configuration instance.

    Returns:
        Configuration singleton
    """
    global _config
    if _config is None:
        _config = load_config()
    return _config


def reload_config(config_path: Optional[Path] = None) -> AgentSystemConfig:
    """
    Reload configuration from file.

    Args:
        config_path: Path to config file

    Returns:
        Reloaded configuration
    """
    global _config
    _config = load_config(config_path)
    return _config
