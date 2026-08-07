from dataclasses import dataclass
from typing import Dict, List


@dataclass
class Permission:
    key: str
    description: str


class PermissionRegistry:
    def __init__(self) -> None:
        self._perms: Dict[str, Permission] = {}

    def register(self, key: str, description: str) -> None:
        self._perms[key] = Permission(key=key, description=description)

    def list(self) -> List[Permission]:
        return list(self._perms.values())

    def get(self, key: str) -> Permission | None:
        return self._perms.get(key)


registry = PermissionRegistry()

# default permissions
registry.register("automation.open_app", "Permite abrir aplicações via automação")
registry.register("automation.click", "Permite enviar cliques ao sistema")
registry.register("automation.delete_file", "Permite exclusão de arquivos")
registry.register("search.web", "Permite buscas na web")
registry.register("file.read", "Permite leitura de arquivos")
registry.register("file.write", "Permite criação e escrita de arquivos")
registry.register("file.delete", "Permite exclusão de arquivos pelo plugin")
registry.register("voice.tts", "Permite síntese de voz de respostas")
registry.register("voice.stt", "Permite reconhecimento de fala via microfone")
