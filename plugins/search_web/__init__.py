import re
import webbrowser
import urllib.parse
from core.plugin_loader import Plugin
from core.event_bus import Event
from core.logger import get_logger
from skills import registry as skill_registry
import security.manager as security_manager

logger = get_logger("plugin.search_web")

SEARCH_PREFIX = re.compile(
    r"^(?:buscar?|busque|pesquisar?|pesquise|procurar?|procure|googlar|googla|joga no google)"
    r"(?:\s+(?:no|na)\s+(?:google|internet|web|bing))?(?:\s+(?:sobre|por))?\s+",
    re.IGNORECASE,
)
MEDIA_PREFIX = re.compile(r"^buscar\s+(?:música|musica|vídeo|video)\s", re.IGNORECASE)


class SearchWebPlugin(Plugin):
    name = "search_web"
    version = "1.0.0"
    description = "Busca na web: 'buscar ...', 'pesquisa ...', 'procura no google ...'"

    def setup(self, event_bus) -> None:
        self._event_bus = event_bus
        event_bus.subscribe("user_message", self._on_user_message)

    @staticmethod
    def extract_query(text: str) -> str | None:
        match = SEARCH_PREFIX.match(text.strip())
        if not match or MEDIA_PREFIX.match(text.strip()):
            return None
        return text.strip()[match.end() :].strip() or None

    def _on_user_message(self, event: Event) -> None:
        try:
            payload = event.payload or {}
            text = (payload.get("text") or "").strip()
            query = self.extract_query(text)
            if not query or skill_registry.match(text) is not None:
                return
            if security_manager.manager and not security_manager.manager.is_allowed("search.web"):
                self._event_bus.publish_sync(
                    Event(
                        name="system_message",
                        payload={"text": "Busca na web bloqueada pela política de permissões."},
                        source="jarvis",
                    )
                )
                return
            url = "https://www.google.com/search?q=" + urllib.parse.quote_plus(query)
            webbrowser.open_new_tab(url)
            logger.info("Busca web: %s", query)
            self._event_bus.publish_sync(Event(name="system_message", payload={"text": f"Pesquisando: {query}"}, source="jarvis"))
        except Exception:
            logger.exception("Erro no plugin search_web")
