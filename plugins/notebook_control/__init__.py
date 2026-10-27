"""Controle do notebook por voz ou texto.

Registra no `skills.registry` os comandos de volume, mídia, brilho, energia,
janelas, teclado, aplicativos, status do sistema e terminal. Quem executa é o
`SkillRouter` do núcleo (ou o agente de IA, via tool use), sempre passando por
permissões e, nas ações destrutivas, pela confirmação.
"""

from __future__ import annotations

import re

from core.event_bus import EventBus
from core.logger import get_logger
from core.plugin_loader import Plugin
from core.text import NUMBER_PATTERN as N
from core.text import parse_number
from media.manager import MediaManager
from skills import Skill, SkillRegistry, registry as default_registry
from system.controller import KEY_NAMES, SHORTCUTS, SystemController

logger = get_logger("plugin.notebook_control")

PCT = r"(?:\s*%|\s+por\s*cento)?"
DEVICE = r"(?:o\s+|a\s+)?(?:computador|notebook|note|pc|windows|maquina)"
IN_MINUTES = rf"(?:\s+(?:em|daqui a|daqui)\s+(?P<minutes>{N})\s+minutos?)?"

# variações faladas → nome canônico do atalho em SHORTCUTS
SHORTCUT_PHRASES: list[tuple[str, str]] = [
    (r"(?:copia|copiar|copie)(?:\s+(?:isso|isto|o texto|tudo))?", "copiar"),
    (r"(?:cola|colar|cole)(?:\s+(?:isso|aqui|o texto))?", "colar"),
    (r"(?:recorta|recortar|recorte)(?:\s+(?:isso|isto))?", "recortar"),
    (r"(?:desfaz|desfazer|desfaca)(?:\s+(?:isso|a ultima coisa))?", "desfazer"),
    (r"(?:refaz|refazer|refaca)", "refazer"),
    (r"(?:salva|salvar|salve)(?:\s+(?:isso|o arquivo|o documento|tudo))?", "salvar"),
    (r"(?:seleciona|selecionar|selecione)\s+tudo", "selecionar tudo"),
    (r"(?:abre|abrir|abra)\s+(?:uma\s+)?nova\s+aba|nova aba", "nova aba"),
    (r"(?:fecha|fechar|feche)\s+(?:a\s+|essa\s+|esta\s+)?aba", "fechar aba"),
    (r"(?:reabre|reabrir|reabra)\s+(?:a\s+)?aba(?:\s+fechada)?", "reabrir aba"),
    (r"(?:proxima|muda de|mudar de|vai pra proxima)\s+aba", "proxima aba"),
    (r"aba anterior|volta(?:r)?\s+(?:pra|para a)\s+aba anterior", "aba anterior"),
    (r"(?:atualiza|atualizar|atualize|recarrega|recarregar|recarregue)\s+(?:a\s+)?pagina", "atualizar pagina"),
    (r"(?:volta|voltar|volte)\s+(?:a\s+|uma\s+)?pagina", "voltar pagina"),
    (r"(?:avanca|avancar|avance)\s+(?:a\s+|uma\s+)?pagina", "avancar pagina"),
    (r"(?:coloca em |ativa |ativar |modo )?tela cheia", "tela cheia"),
    (r"(?:procura|procurar|procure|busca|buscar)\s+na\s+pagina", "procurar na pagina"),
    (r"(?:imprime|imprimir|imprima)(?:\s+(?:isso|a pagina|o documento))?", "imprimir"),
    (r"(?:abre|abrir|abra)\s+(?:uma\s+)?nova\s+janela|nova janela", "nova janela"),
    (r"(?:minimiza|minimizar|minimize)\s+tudo|(?:mostra|mostrar|mostre|vai para a|ir para a)\s+(?:a\s+)?area de trabalho", "minimizar tudo"),
    (r"(?:troca|trocar|troque|muda|mudar|mude|alterna|alternar|alterne)\s+de\s+janela|proxima janela", "trocar de janela"),
    (r"(?:fecha|fechar|feche)\s+(?:a\s+|essa\s+|esta\s+)?janela", "fechar janela"),
    (r"(?:maximiza|maximizar|maximize)\s+(?:a\s+|essa\s+|esta\s+)?janela", "maximizar janela"),
    (r"(?:minimiza|minimizar|minimize)\s+(?:a\s+|essa\s+|esta\s+)?janela", "minimizar janela"),
    (r"(?:abre|abrir|abra)\s+o\s+gerenciador de tarefas|gerenciador de tarefas", "gerenciador de tarefas"),
    (r"(?:abre|abrir|abra)\s+(?:as\s+)?configuracoes rapidas|configuracoes rapidas", "configuracoes rapidas"),
    (r"(?:abre|abrir|abra)\s+(?:a\s+)?central de notificacoes|notificacoes", "central de notificacoes"),
    (r"(?:abre|abrir|abra)\s+(?:os\s+)?emojis?|emojis?", "emoji"),
]
_SHORTCUT_REGEXES = [(re.compile(rf"^(?:{pattern})$"), name) for pattern, name in SHORTCUT_PHRASES]


def _match_shortcut(normalized: str) -> dict[str, str] | None:
    for pattern, name in _SHORTCUT_REGEXES:
        if pattern.match(normalized):
            return {"atalho": name}
    return None


def _num(params: dict[str, str], key: str, default: int | None = None) -> int | None:
    value = parse_number(params.get(key))
    return default if value is None else value


def build_skills(controller: SystemController, media: MediaManager) -> list[Skill]:
    """Cria as skills de controle do notebook (ordem importa: específicas antes das genéricas)."""

    def set_volume(params: dict[str, str]) -> str:
        percent = _num(params, "percent")
        if percent is None:
            raise ValueError("Diga um valor entre 0 e 100.")
        return controller.set_volume(percent)

    def set_brightness(params: dict[str, str]) -> str:
        percent = _num(params, "percent")
        if percent is None:
            raise ValueError("Diga um valor entre 0 e 100.")
        return controller.set_brightness(percent)

    def press_key(params: dict[str, str]) -> str:
        return controller.press_key(params["tecla"], _num(params, "vezes", 1) or 1)

    def scroll(params: dict[str, str]) -> str:
        verb = params.get("verbo", "")
        direction = params.get("direcao") or ("cima" if verb.startswith(("sob", "sub", "suba")) else "baixo")
        return controller.scroll(direction)

    def dark_mode(params: dict[str, str]) -> str:
        return controller.set_dark_mode(params.get("tema") in ("escuro", "noturno", "dark"))

    def play_song(params: dict[str, str]) -> str:
        media.search(params["musica"], "music")
        return f"Abrindo {params['musica']} no YouTube Music."

    return [
        # ------------------------------------------------------------ volume
        Skill(
            name="volume.definir",
            description="Ajusta o volume do Windows para uma porcentagem exata (0 a 100).",
            patterns=[
                rf"(?:(?:coloca|colocar|coloque|deixa|deixar|deixe|ajusta|ajustar|ajuste|muda|mudar|mude|bota|botar|poe)\s+)?(?:o\s+)?(?:volume|som)\s+(?:em|para|no|pra|a|pro)\s+(?P<percent>{N}){PCT}",
                rf"(?:aumenta|aumentar|aumente|sobe|diminui|diminuir|diminua|abaixa|abaixar|abaixe|baixa)\s+(?:o\s+)?(?:volume|som)\s+(?:para|pra|ate)\s+(?P<percent>{N}){PCT}",
                rf"volume\s+(?P<percent>{N}){PCT}",
            ],
            parameters={"percent": "Porcentagem do volume, de 0 a 100"},
            required=["percent"],
            handler=set_volume,
            permission="media.control",
            examples=["volume em 50", "coloca o volume para 30"],
            category="som",
        ),
        Skill(
            name="volume.aumentar",
            description="Aumenta o volume do Windows (padrão 10%).",
            patterns=[
                rf"(?:aumenta|aumentar|aumente|sobe|subir|suba|levanta)\s+(?:o\s+|um pouco o\s+)?(?:volume|som)(?:\s+um pouco)?(?:\s+em\s+(?P<percent>{N}){PCT})?",
                r"(?:volume|som)\s+mais\s+alto|mais\s+alto|mais\s+volume",
            ],
            parameters={"percent": "Quanto aumentar, em porcentagem (opcional)"},
            handler=lambda p: controller.volume_up(_num(p, "percent")),
            permission="media.control",
            examples=["aumentar o volume", "aumenta o volume em 20"],
            category="som",
        ),
        Skill(
            name="volume.diminuir",
            description="Diminui o volume do Windows (padrão 10%).",
            patterns=[
                rf"(?:diminui|diminuir|diminua|abaixa|abaixar|abaixe|baixa|baixar|baixe|reduz|reduzir|reduza)\s+(?:o\s+|um pouco o\s+)?(?:volume|som)(?:\s+um pouco)?(?:\s+em\s+(?P<percent>{N}){PCT})?",
                r"(?:volume|som)\s+mais\s+baixo|mais\s+baixo|menos\s+volume",
            ],
            parameters={"percent": "Quanto diminuir, em porcentagem (opcional)"},
            handler=lambda p: controller.volume_down(_num(p, "percent")),
            permission="media.control",
            examples=["diminuir o volume", "abaixa o som"],
            category="som",
        ),
        Skill(
            name="volume.mudo",
            description="Liga ou desliga o mudo do Windows.",
            patterns=[
                r"(?:muta|mutar|mute|silencia|silenciar|silencie|desmuta|desmutar|desmute|(?:tira|tirar|tire|ativa|ativar|ative|liga|ligar)\s+o\s+mudo|mudo)(?:\s+(?:o\s+)?(?:som|audio|volume|computador|notebook))?",
                r"(?:desliga|desligar|desligue|liga|ligar|ligue|corta|cortar|corte)\s+o\s+(?:som|audio)",
            ],
            handler=lambda p: controller.toggle_mute(),
            permission="media.control",
            examples=["mutar o som", "tira o mudo"],
            category="som",
        ),
        # ------------------------------------------------------------ mídia
        Skill(
            name="midia.pausar_tocar",
            description="Pausa ou retoma a música/vídeo que está tocando.",
            patterns=[
                r"(?:pausa|pausar|pause|para|parar|pare)\s+(?:a\s+|o\s+)?(?:musica|midia|video|som|reproducao|spotify|youtube)",
                r"(?:toca|tocar|toque|continua|continuar|continue|retoma|retomar|retome|despausa|despausar|play|da play|dar play|solta o som)(?:\s+(?:a\s+|o\s+)?(?:musica|midia|video|reproducao))?",
                r"pausa|pausar|pause",
            ],
            handler=lambda p: controller.media("play_pause"),
            permission="media.control",
            examples=["pausar a música", "continuar a música"],
            category="mídia",
        ),
        Skill(
            name="midia.proxima",
            description="Pula para a próxima faixa.",
            patterns=[
                r"(?:proxima|pula|pular|pule|passa|passar|passe|avanca|avancar)\s+(?:a\s+|essa\s+|esta\s+)?(?:musica|faixa|video)?(?:\s+seguinte)?",
                r"(?:musica|faixa)\s+seguinte",
            ],
            handler=lambda p: controller.media("next"),
            permission="media.control",
            examples=["próxima música"],
            category="mídia",
        ),
        Skill(
            name="midia.anterior",
            description="Volta para a faixa anterior.",
            patterns=[
                r"(?:musica|faixa|video)\s+anterior",
                r"(?:volta|voltar|volte)\s+(?:a\s+)?(?:musica|faixa)",
            ],
            handler=lambda p: controller.media("previous"),
            permission="media.control",
            examples=["música anterior"],
            category="mídia",
        ),
        Skill(
            name="midia.tocar_musica",
            description="Procura e abre uma música ou artista no YouTube Music.",
            patterns=[
                r"(?:toca|tocar|toque|reproduz|reproduzir|reproduza|quero ouvir|ouvir|escutar|bota pra tocar|coloca pra tocar|poe pra tocar)\s+(?:a\s+musica\s+|musica\s+|a\s+|o\s+)?(?P<musica>.+)",
            ],
            parameters={"musica": "Nome da música, artista ou playlist"},
            required=["musica"],
            raw_params=["musica"],
            handler=play_song,
            permission="media.search",
            examples=["tocar Legião Urbana"],
            category="mídia",
        ),
        # ------------------------------------------------------------ brilho
        Skill(
            name="brilho.definir",
            description="Ajusta o brilho da tela do notebook para uma porcentagem.",
            patterns=[
                rf"(?:(?:coloca|colocar|coloque|deixa|deixar|deixe|ajusta|ajustar|ajuste|muda|mudar|mude|bota)\s+)?(?:o\s+)?brilho(?:\s+da\s+tela)?\s+(?:em|para|no|pra|a)\s+(?P<percent>{N}){PCT}",
                rf"(?:aumenta|aumentar|aumente|sobe|diminui|diminuir|diminua|abaixa|abaixar|abaixe)\s+(?:o\s+)?brilho(?:\s+da\s+tela)?\s+(?:para|pra|ate)\s+(?P<percent>{N}){PCT}",
            ],
            parameters={"percent": "Porcentagem do brilho, de 0 a 100"},
            required=["percent"],
            handler=set_brightness,
            permission="system.brightness",
            examples=["brilho em 70"],
            category="tela",
        ),
        Skill(
            name="brilho.aumentar",
            description="Aumenta o brilho da tela em 20%.",
            patterns=[
                r"(?:aumenta|aumentar|aumente|sobe|subir|suba)\s+(?:o\s+)?brilho(?:\s+da\s+tela)?",
                r"(?:(?:deixa|deixe|deixar|coloca|bota)\s+)?(?:a\s+|o\s+)?(?:tela|brilho)\s+mais\s+(?:clara|claro|forte|alto)",
            ],
            handler=lambda p: controller.change_brightness(20),
            permission="system.brightness",
            examples=["aumentar o brilho"],
            category="tela",
        ),
        Skill(
            name="brilho.diminuir",
            description="Diminui o brilho da tela em 20%.",
            patterns=[
                r"(?:diminui|diminuir|diminua|abaixa|abaixar|abaixe|baixa|reduz|reduzir|reduza)\s+(?:o\s+)?brilho(?:\s+da\s+tela)?",
                r"(?:(?:deixa|deixe|deixar|coloca|bota)\s+)?(?:a\s+|o\s+)?(?:tela|brilho)\s+mais\s+(?:escura|escuro|fraco|baixo)",
            ],
            handler=lambda p: controller.change_brightness(-20),
            permission="system.brightness",
            examples=["diminuir o brilho"],
            category="tela",
        ),
        Skill(
            name="tema.escuro_claro",
            description="Ativa o modo escuro ou claro do Windows.",
            patterns=[
                r"(?:(?:ativa|ativar|ative|liga|ligar|ligue|coloca|colocar|coloque|muda para|mudar para|mude para|usa|usar)\s+)?(?:o\s+)?(?:modo|tema)\s+(?P<tema>escuro|claro|noturno|dark|light)",
            ],
            parameters={"tema": "'escuro' ou 'claro'"},
            required=["tema"],
            handler=dark_mode,
            permission="system.settings",
            examples=["ativar modo escuro"],
            category="tela",
        ),
        Skill(
            name="tela.print",
            description="Tira um print (captura) da tela e salva em Imagens/Jarvis.",
            patterns=[
                r"(?:tira|tirar|tire|faz|fazer|faca|bate|bater|bata)\s+(?:um\s+|uma\s+)?(?:print|printscreen|print screen|captura de tela|screenshot|foto da tela)(?:\s+da\s+tela)?",
                r"(?:print|captura|capturar|captura de)\s+(?:da\s+|a\s+)?tela|printscreen|screenshot",
            ],
            handler=lambda p: controller.screenshot(),
            permission="system.screenshot",
            examples=["tirar um print"],
            category="tela",
        ),
        # ------------------------------------------------------------ energia
        Skill(
            name="energia.bloquear",
            description="Bloqueia a tela do Windows.",
            patterns=[rf"(?:bloqueia|bloquear|bloqueie|trava|travar|trave)\s+(?:a\s+)?(?:tela|{DEVICE})"],
            handler=lambda p: controller.lock(),
            permission="system.lock",
            examples=["bloquear a tela"],
            category="energia",
        ),
        Skill(
            name="energia.suspender",
            description="Coloca o computador em suspensão.",
            patterns=[
                rf"(?:suspende|suspender|suspenda|hiberna|hibernar|hiberne)(?:\s+{DEVICE})?",
                r"(?:modo\s+)?(?:suspensao|hibernacao)",
                rf"(?:coloca|colocar|coloque|bota)\s+{DEVICE}\s+(?:pra|para)\s+dormir",
            ],
            handler=lambda p: controller.sleep(),
            permission="system.sleep",
            confirm_key="system.sleep",
            confirm_text="Suspender o computador agora",
            examples=["suspender o computador"],
            category="energia",
        ),
        Skill(
            name="energia.desligar",
            description="Desliga o computador, agora ou em alguns minutos.",
            patterns=[rf"(?:desliga|desligar|desligue)\s+{DEVICE}{IN_MINUTES}"],
            parameters={"minutes": "Minutos até desligar (opcional, padrão agora)"},
            handler=lambda p: controller.shutdown(_num(p, "minutes", 0) or 0),
            permission="system.shutdown",
            confirm_key="system.shutdown",
            confirm_text=lambda p: (
                f"Desligar o computador em {p['minutes']} minuto(s)" if p.get("minutes") else "Desligar o computador agora"
            ),
            examples=["desligar o computador em 30 minutos"],
            category="energia",
        ),
        Skill(
            name="energia.reiniciar",
            description="Reinicia o computador, agora ou em alguns minutos.",
            patterns=[rf"(?:reinicia|reiniciar|reinicie)\s+{DEVICE}{IN_MINUTES}"],
            parameters={"minutes": "Minutos até reiniciar (opcional)"},
            handler=lambda p: controller.restart(_num(p, "minutes", 0) or 0),
            permission="system.restart",
            confirm_key="system.restart",
            confirm_text="Reiniciar o computador",
            examples=["reiniciar o computador"],
            category="energia",
        ),
        Skill(
            name="energia.cancelar_desligamento",
            description="Cancela um desligamento ou reinício agendado.",
            patterns=[r"(?:cancela|cancelar|cancele|aborta|abortar|aborte)\s+(?:o\s+)?(?:desligamento|reinicio)(?:\s+agendado)?|nao desliga(?:r)?"],
            handler=lambda p: controller.cancel_shutdown(),
            permission="system.shutdown",
            examples=["cancelar desligamento"],
            category="energia",
        ),
        # ------------------------------------------------------------ janelas e teclado
        Skill(
            name="janela.atalho",
            description=(
                "Executa um atalho de teclado/janela. Valores de 'atalho': " + ", ".join(SHORTCUTS) + "."
            ),
            matcher=_match_shortcut,
            parameters={"atalho": "Nome do atalho (ex.: copiar, colar, nova aba, minimizar tudo)"},
            required=["atalho"],
            handler=lambda p: controller.shortcut(p["atalho"]),
            permission="automation.hotkey",
            examples=["copiar", "colar", "nova aba", "minimizar tudo", "trocar de janela", "fechar janela"],
            category="janelas",
        ),
        Skill(
            name="teclado.apertar",
            description="Pressiona uma tecla (enter, esc, tab, espaço, setas, F5...) uma ou mais vezes.",
            patterns=[
                rf"(?:aperta|apertar|aperte|pressiona|pressionar|pressione|tecla|da um|dar um|clica em|clicar em|clique em)\s+(?:a\s+tecla\s+|o\s+|a\s+)?(?P<tecla>{'|'.join(sorted(KEY_NAMES, key=len, reverse=True))})(?:\s+(?P<vezes>{N})\s+vezes)?",
            ],
            parameters={"tecla": "Tecla a pressionar", "vezes": "Quantas vezes (opcional)"},
            required=["tecla"],
            handler=press_key,
            permission="automation.hotkey",
            examples=["apertar enter"],
            category="janelas",
        ),
        Skill(
            name="teclado.digitar",
            description="Digita um texto onde o cursor estiver.",
            patterns=[r"(?:digita|digitar|digite|escreve|escrever|escreva)\s+(?:ai\s+|aqui\s+|o texto\s+)?(?P<texto>.+)"],
            parameters={"texto": "Texto exato a digitar"},
            required=["texto"],
            raw_params=["texto"],
            handler=lambda p: controller.type_text(p["texto"]),
            permission="automation.type_text",
            examples=["digitar bom dia a todos"],
            category="janelas",
        ),
        Skill(
            name="tela.rolar",
            description="Rola a página para cima ou para baixo.",
            patterns=[
                r"(?P<verbo>rola|rolar|role|desce|descer|desca|sobe|subir|suba)\s+(?:a\s+)?(?:pagina|tela)(?:\s+(?:para|pra)\s+(?P<direcao>baixo|cima))?",
            ],
            parameters={"direcao": "'cima' ou 'baixo'"},
            handler=scroll,
            permission="automation.hotkey",
            examples=["descer a página"],
            category="janelas",
        ),
        Skill(
            name="app.fechar",
            description="Fecha um aplicativo aberto pelo nome (chrome, word, spotify...).",
            patterns=[r"(?:fecha|fechar|feche|encerra|encerrar|encerre|mata|matar|mate)\s+(?:o\s+|a\s+)?(?:programa\s+|aplicativo\s+|app\s+)?(?P<app>.+)"],
            parameters={"app": "Nome do aplicativo"},
            required=["app"],
            handler=lambda p: controller.close_app(p["app"]),
            permission="system.close_app",
            examples=["fechar o chrome"],
            category="aplicativos",
        ),
        # ------------------------------------------------------------ informações
        Skill(
            name="sistema.bateria",
            description="Informa o nível e o estado da bateria.",
            patterns=[r"(?:.*\s)?bateria(?:\s.*)?"],
            handler=lambda p: controller.battery(),
            permission="system.info",
            examples=["como está a bateria"],
            category="informações",
        ),
        Skill(
            name="sistema.status",
            description="Mostra uso de CPU, memória, disco e bateria.",
            patterns=[
                rf"(?:status|estado|situacao|desempenho)\s+(?:do\s+)?(?:sistema|computador|notebook|pc)",
                rf"como\s+(?:esta|ta)\s+{DEVICE}",
                r"(?:.*\s)?uso\s+de\s+(?:cpu|memoria|processador|ram)(?:\s.*)?",
                r"(?:quanto de |quanta )?(?:memoria|ram)\s+(?:livre|disponivel|em uso|esta sendo usada)",
            ],
            handler=lambda p: controller.system_status(),
            permission="system.info",
            examples=["status do sistema"],
            category="informações",
        ),
        Skill(
            name="sistema.disco",
            description="Mostra o espaço livre nos discos.",
            patterns=[r"(?:.*\s)?(?:espaco\s+(?:em|no|livre)(?:\s+(?:no\s+|em\s+)?disco)?|armazenamento)(?:\s.*)?"],
            handler=lambda p: controller.disk_space(),
            permission="system.info",
            examples=["quanto espaço livre tenho"],
            category="informações",
        ),
        Skill(
            name="sistema.rede",
            description="Informa se há internet, a rede Wi-Fi e o IP local.",
            patterns=[
                r"(?:qual\s+(?:e\s+)?)?(?:o\s+)?meu\s+ip",
                r"(?:to|tou|estou|esta|ta)\s+(?:conectado|com internet|sem internet|online|offline)",
                r"(?:como\s+(?:esta|ta)\s+)?(?:a\s+)?(?:internet|rede|conexao|wifi|wi fi)(?:\s+(?:esta|ta)\s+funcionando)?",
                r"tem internet|status da (?:internet|rede|conexao)",
            ],
            handler=lambda p: controller.network(),
            permission="system.info",
            examples=["estou conectado"],
            category="informações",
        ),
        Skill(
            name="sistema.processos",
            description="Lista os processos que mais consomem memória.",
            patterns=[
                r"(?:quais|que)\s+(?:sao\s+)?(?:os\s+)?(?:programas|processos)\s+(?:mais\s+)?(?:pesados|abertos|consumindo.*|usando.*)",
                r"o\s+que\s+(?:esta|ta)\s+(?:consumindo|usando|pesando|travando).*",
                r"processos(?:\s+mais)?\s+pesados",
            ],
            handler=lambda p: controller.top_processes(),
            permission="system.info",
            examples=["o que está pesando o computador"],
            category="informações",
        ),
        Skill(
            name="sistema.info",
            description="Mostra nome, sistema operacional e processador do computador.",
            patterns=[
                r"(?:informacoes|info|dados|especificacoes)\s+(?:do\s+)?(?:computador|sistema|notebook|pc)",
                r"qual\s+(?:e\s+)?(?:o\s+)?meu\s+(?:computador|sistema|processador|windows)",
            ],
            handler=lambda p: controller.computer_info(),
            permission="system.info",
            examples=["informações do computador"],
            category="informações",
        ),
        Skill(
            name="clipboard.ler",
            description="Lê o texto que está na área de transferência.",
            patterns=[
                r"(?:le|ler|leia|mostra|mostrar|mostre)\s+(?:a\s+|o\s+)?(?:area de transferencia|clipboard|que (?:eu )?copiei)",
                r"o\s+que\s+(?:eu\s+)?copiei|o\s+que\s+(?:tem|esta|ta)\s+na\s+area de transferencia",
            ],
            handler=lambda p: controller.read_clipboard(),
            permission="clipboard.read",
            examples=["o que eu copiei"],
            category="informações",
        ),
        # ------------------------------------------------------------ arquivos e terminal
        Skill(
            name="arquivos.criar_pasta",
            description="Cria uma pasta na área de trabalho, documentos, downloads, imagens, músicas ou vídeos.",
            patterns=[
                r"(?:cria|criar|crie|faz|fazer|faca)\s+(?:uma\s+)?(?:nova\s+)?pasta\s+(?:chamada\s+|com o nome\s+|de nome\s+)?(?P<nome>.+?)(?:\s+(?:na|no|em)\s+(?P<local>area de trabalho|desktop|documentos|downloads|imagens|musicas|videos))?",
            ],
            parameters={"nome": "Nome da pasta", "local": "area de trabalho, documentos, downloads, imagens, musicas ou videos"},
            required=["nome"],
            raw_params=["nome"],
            handler=lambda p: controller.create_folder(p["nome"], p.get("local")),
            permission="file.write",
            examples=["criar pasta Projetos na área de trabalho"],
            category="arquivos",
        ),
        Skill(
            name="terminal.executar",
            description="Executa um comando do PowerShell e devolve a saída. Exige permissão terminal.run e confirmação.",
            patterns=[r"(?:executa|executar|execute|roda|rodar|rode)\s+(?:o\s+)?comando\s+(?P<comando>.+)"],
            parameters={"comando": "Comando PowerShell exato"},
            required=["comando"],
            raw_params=["comando"],
            handler=lambda p: controller.run_command(p["comando"]),
            permission="terminal.run",
            confirm_key="terminal.run",
            confirm_text=lambda p: f"Executar no PowerShell: {p.get('comando', '')}",
            examples=["executar comando ipconfig"],
            category="terminal",
        ),
    ]


class NotebookControlPlugin(Plugin):
    name = "notebook_control"
    version = "1.0.0"
    description = "Controla volume, brilho, energia, janelas, teclado, apps e status do notebook."

    def __init__(self, registry: SkillRegistry | None = None, controller: SystemController | None = None) -> None:
        self._registry = registry or default_registry
        self._media = MediaManager()
        self._controller = controller or SystemController(media=self._media)
        self._names: list[str] = []

    def setup(self, event_bus: EventBus) -> None:
        for skill in build_skills(self._controller, self._media):
            self._registry.register(skill)
            self._names.append(skill.name)
        logger.info("%d comandos de controle do notebook registrados", len(self._names))

    def teardown(self) -> None:
        for name in self._names:
            self._registry.unregister(name)
