from dataclasses import dataclass
from typing import Dict, List


@dataclass
class Permission:
    key: str
    description: str
    default: bool = True


class PermissionRegistry:
    def __init__(self) -> None:
        self._perms: Dict[str, Permission] = {}

    def register(self, key: str, description: str, default: bool = True) -> None:
        self._perms[key] = Permission(key=key, description=description, default=default)

    def list(self) -> List[Permission]:
        return list(self._perms.values())

    def get(self, key: str) -> Permission | None:
        return self._perms.get(key)


registry = PermissionRegistry()

# default permissions
registry.register("automation.open_app", "Permite abrir aplicações via automação")
registry.register("automation.click", "Permite enviar cliques ao sistema")
registry.register("automation.type_text", "Permite digitar texto no sistema")
registry.register("automation.hotkey", "Permite enviar atalhos de teclado")
registry.register("automation.delete_file", "Permite exclusão de arquivos")
registry.register("search.web", "Permite buscas na web")
registry.register("browser.read", "Permite ler texto de páginas públicas")
registry.register("vision.ocr", "Permite reconhecer texto em imagens locais")
registry.register("communication.email_draft", "Permite abrir rascunhos no cliente de e-mail")
registry.register("media.search", "Permite pesquisar música e vídeo no navegador")
registry.register("media.control", "Permite controlar reprodução e volume do Windows")
registry.register("file.read", "Permite leitura de arquivos")
registry.register("file.write", "Permite criação e escrita de arquivos")
registry.register("file.delete", "Permite exclusão de arquivos pelo plugin")
registry.register("voice.tts", "Permite síntese de voz de respostas")
registry.register("voice.stt", "Permite reconhecimento de fala via microfone")

# controle do notebook
registry.register("system.info", "Permite consultar bateria, CPU, memória, disco e rede")
registry.register("system.brightness", "Permite ajustar o brilho da tela")
registry.register("system.screenshot", "Permite capturar a tela")
registry.register("system.lock", "Permite bloquear a sessão do Windows")
registry.register("system.sleep", "Permite suspender o computador")
registry.register("system.shutdown", "Permite desligar o computador")
registry.register("system.restart", "Permite reiniciar o computador")
registry.register("system.close_app", "Permite fechar aplicativos abertos")
registry.register("system.settings", "Permite alterar preferências do Windows, como o tema escuro")
registry.register("clipboard.read", "Permite ler a área de transferência")
registry.register("notes.write", "Permite criar notas e lembretes")
registry.register("notes.read", "Permite ler notas salvas")
registry.register("notes.clear", "Permite apagar todas as notas")
registry.register(
    "terminal.run",
    "Permite executar comandos do PowerShell ditados por você (sempre pede confirmação)",
    default=False,
)
