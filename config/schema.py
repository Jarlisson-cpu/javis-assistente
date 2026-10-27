"""Modelos Pydantic que definem o formato validado da configuração do JARVIS."""

from __future__ import annotations

from pydantic import BaseModel, Field


class AppConfig(BaseModel):
    name: str = "JARVIS"
    version: str = "1.0.0"
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
    permissions_file: str = "data/permissions.json"


class PluginsConfig(BaseModel):
    directory: str = "plugins"
    autoload: bool = True
    enabled: list[str] = Field(default_factory=list)
    disabled: list[str] = Field(default_factory=list)


class VoiceConfig(BaseModel):
    stt_engine: str = "auto"  # auto | vosk | google
    tts_engine: str = "auto"  # auto | pyttsx3 | windows
    language: str = "pt-BR"
    stt_model_path: str = "models/vosk"
    stt_sample_rate: int = 16000
    wake_word: str = "jarvis"
    wake_word_aliases: list[str] = Field(default_factory=lambda: ["jarvis", "jarbas", "jarves", "javis", "djarvis"])
    enable_tts: bool = True
    enable_stt: bool = False
    tts_rate: int = 190
    tts_voice: str = ""  # trecho do nome da voz; vazio = primeira voz em português
    speak_max_chars: int = 600
    listen_seconds: int = 6
    phrase_seconds: int = 15
    silence_seconds: float = 0.9
    conversation_timeout_seconds: int = 25
    beep: bool = True


class MemoryConfig(BaseModel):
    db_path: str = "jarvis_memory.db"
    vector_enabled: bool = False
    vector_path: str = "database/vectors"
    vector_collection: str = "jarvis_memory"
    embedding_model: str = "all-MiniLM-L6-v2"


class UsersConfig(BaseModel):
    default_user: str = ""  # usuário local usado sem senha no terminal/voz; vazio = o único/primeiro admin
    require_password_locally: bool = False
    web_login_required: bool = True
    session_hours: float = 12


class AIConfig(BaseModel):
    provider: str = "auto"  # auto | anthropic | openai | gemini | offline
    model: str = ""  # vazio = modelo padrão do provedor


class RootConfig(BaseModel):
    """Raiz da configuração validada, espelhando a estrutura de config.yaml."""

    app: AppConfig = Field(default_factory=AppConfig)
    logging: LoggingConfig = Field(default_factory=LoggingConfig)
    security: SecurityConfig = Field(default_factory=SecurityConfig)
    plugins: PluginsConfig = Field(default_factory=PluginsConfig)
    voice: VoiceConfig = Field(default_factory=VoiceConfig)
    memory: MemoryConfig = Field(default_factory=MemoryConfig)
    users: UsersConfig = Field(default_factory=UsersConfig)
    ai: AIConfig = Field(default_factory=AIConfig)
