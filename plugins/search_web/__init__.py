import webbrowser
import urllib.parse
from core.plugin_loader import Plugin
from core.event_bus import Event
from core.logger import get_logger

logger = get_logger("plugin.search_web")


class SearchWebPlugin(Plugin):
    name = "search_web"
    version = "0.1.0"
    description = "Busca rápida na web a partir de mensagens começando com 'buscar '"

    def setup(self, event_bus) -> None:
        self._event_bus = event_bus
        event_bus.subscribe("user_message", self._on_user_message)

    def _on_user_message(self, event: Event) -> None:
        try:
            payload = event.payload or {}
            text = (payload.get("text") or "").strip()
            if not text.lower().startswith("buscar "):
                return
            query = text[len("buscar ") :].strip()
            if not query:
                return
            url = "https://www.bing.com/search?q=" + urllib.parse.quote_plus(query)
            webbrowser.open_new_tab(url)
            logger.info("Busca web: %s", query)
            self._event_bus.publish_sync(Event(name="system_message", payload={"text": f"Buscando: {query}"}, source="jarvis"))
        except Exception:
            logger.exception("Erro no plugin search_web")
