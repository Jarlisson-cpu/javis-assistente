"""Modelos Pydantic que definem o formato validado da configuração do JARVIS."""

from __future__ import annotations

from pydantic import BaseModel, Field


class AppConfig(BaseModel):
    name: str = "JARVIS"
    version: str = "0.1.0"
    environment: str = "development"


class LoggingConfig(BaseModel):
    level: str = "INFO"
    directory: str = "logs"
    max_file_size_mb: int = 10
    backup_count: int = 5
    console_output: bool = True


class SecurityConfig(BaseModel):
    require_confirmation_for: list[str] = Field(default_factory=list)
    confirmation_timeout_seconds: int = 30
    default_deny_on_timeout: bool = True
    permissions: dict[str, bool] = Field(default_factory=dict)


class PluginsConfig(BaseModel):
    directory: str = "plugins"
    autoload: bool = True
    enabled: list[str] = Field(default_factory=list)
    disabled: list[str] = Field(default_factory=list)


class VoiceConfig(BaseModel):
    stt_engine: str = "vosk"
    tts_engine: str = "pyttsx3"
    language: str = "pt-BR"
    stt_model_path: str = "models/vosk"
    enable_tts: bool = True
    enable_stt: bool = False


class MemoryConfig(BaseModel):
    db_path: str = "jarvis_memory.db"


class RootConfig(BaseModel):
    """Raiz da configuração validada, espelhando a estrutura de config.yaml."""

    app: AppConfig = Field(default_factory=AppConfig)
    logging: LoggingConfig = Field(default_factory=LoggingConfig)
    security: SecurityConfig = Field(default_factory=SecurityConfig)
    plugins: PluginsConfig = Field(default_factory=PluginsConfig)
    voice: VoiceConfig = Field(default_factory=VoiceConfig)
    memory: MemoryConfig = Field(default_factory=MemoryConfig)
