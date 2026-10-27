"""Produtividade: hora e data, calculadora falada, lembretes, notas e perfil do usuário."""

from __future__ import annotations

import ast
import operator
import re
import threading
from datetime import datetime, timedelta
from typing import Any

from core.event_bus import Event, EventBus
from core.logger import get_logger
from core.plugin_loader import Plugin
from core.text import NUMBER_PATTERN as N
from core.text import parse_number
from memory.notes import NotesStore
from skills import Skill, SkillRegistry, registry as default_registry
from users import context as user_context

logger = get_logger("plugin.productivity")

WEEKDAYS = ["segunda-feira", "terça-feira", "quarta-feira", "quinta-feira", "sexta-feira", "sábado", "domingo"]
MONTHS = [
    "janeiro", "fevereiro", "março", "abril", "maio", "junho",
    "julho", "agosto", "setembro", "outubro", "novembro", "dezembro",
]
UNIT_SECONDS = {"segundo": 1, "minuto": 60, "hora": 3600}
MAX_TIMER_SECONDS = 24 * 3600
NUMBER_WORDS = N.removeprefix(r"\d+|")

_OPERATORS = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
    ast.Pow: operator.pow,
    ast.Mod: operator.mod,
    ast.USub: operator.neg,
    ast.UAdd: operator.pos,
}
_SPOKEN_OPERATORS = [
    (r"\bdividido por\b", "/"),
    (r"\bdivide por\b", "/"),
    (r"\belevado (?:a|ao)\b", "**"),
    (r"\bao quadrado\b", "**2"),
    (r"\bao cubo\b", "**3"),
    (r"\bvezes\b|\bmultiplicado por\b|\bx\b", "*"),
    (r"\bmais\b", "+"),
    (r"\bmenos\b", "-"),
    (r"\bresto de\b|\bmod\b", "%"),
    (r"\bvirgula\b", "."),
]


def _safe_eval(node: ast.AST) -> float:
    if isinstance(node, ast.Expression):
        return _safe_eval(node.body)
    if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)):
        return node.value
    if isinstance(node, ast.BinOp) and type(node.op) in _OPERATORS:
        left, right = _safe_eval(node.left), _safe_eval(node.right)
        if isinstance(node.op, ast.Pow) and abs(right) > 100:
            raise ValueError("Expoente grande demais.")
        return _OPERATORS[type(node.op)](left, right)
    if isinstance(node, ast.UnaryOp) and type(node.op) in _OPERATORS:
        return _OPERATORS[type(node.op)](_safe_eval(node.operand))
    raise ValueError("Só sei fazer contas com números e + - × ÷ e potência.")


def calculate(expression: str) -> str:
    """Resolve contas ditas em português ("quinze vezes três", "2 elevado a 10", "20% de 150")."""
    text = expression.strip().lower().rstrip("?.")
    percent = re.fullmatch(rf"(?P<p>{N}|\d+(?:[.,]\d+)?)\s*(?:%|por\s*cento)\s+de\s+(?P<v>{N}|\d+(?:[.,]\d+)?)", text)
    if percent:
        p = parse_number(percent["p"]) if parse_number(percent["p"]) is not None else float(percent["p"].replace(",", "."))
        v = parse_number(percent["v"]) if parse_number(percent["v"]) is not None else float(percent["v"].replace(",", "."))
        return _format_number(p * v / 100)

    for pattern, symbol in _SPOKEN_OPERATORS:
        text = re.sub(pattern, f" {symbol} ", text)
    text = re.sub(r"(\d),(\d)", r"\1.\2", text)
    text = re.sub(rf"\b(?:{NUMBER_WORDS})", lambda m: f" {parse_number(m.group()) if parse_number(m.group()) is not None else m.group()} ", text)
    text = re.sub(r"\s+", " ", text.replace("÷", "/").replace("×", "*")).strip()
    if not re.fullmatch(r"[\d\s.+\-*/%()]+", text):
        raise ValueError("Não entendi a conta. Tente algo como 'quanto é 12 vezes 8'.")
    try:
        result = _safe_eval(ast.parse(text, mode="eval"))
    except ZeroDivisionError as exc:
        raise ValueError("Não dá para dividir por zero.") from exc
    except SyntaxError as exc:
        raise ValueError("Não entendi a conta.") from exc
    return _format_number(result)


def _format_number(value: float) -> str:
    if float(value).is_integer():
        return f"{int(value):,}".replace(",", ".")
    return f"{value:,.4f}".rstrip("0").rstrip(".").replace(",", "X").replace(".", ",").replace("X", ".")


def _greeting_for_hour(hour: int) -> str:
    if hour < 12:
        return "Bom dia"
    if hour < 18:
        return "Boa tarde"
    return "Boa noite"


class ProductivityPlugin(Plugin):
    name = "productivity"
    version = "1.0.0"
    description = "Hora e data, calculadora, lembretes, notas e perfil do usuário."

    def __init__(self, registry: SkillRegistry | None = None, notes: NotesStore | None = None) -> None:
        self._registry = registry or default_registry
        self._notes = notes
        self._event_bus: EventBus | None = None
        self._users: Any = None
        self._timers: list[tuple[datetime, str, threading.Timer]] = []
        self._timers_lock = threading.Lock()
        self._names: list[str] = []

    # ------------------------------------------------------------------ ciclo de vida
    def setup(self, event_bus: EventBus) -> None:
        self._event_bus = event_bus
        for skill in self._build_skills():
            self._registry.register(skill)
            self._names.append(skill.name)

    def attach_core(self, core: Any) -> None:
        """Chamado pelo núcleo após carregar plugins: dá acesso ao banco e aos usuários."""
        self._notes = NotesStore(core.config.memory.db_path)
        self._users = getattr(core, "users", None)

    def teardown(self) -> None:
        with self._timers_lock:
            for _, _, timer in self._timers:
                timer.cancel()
            self._timers.clear()
        for name in self._names:
            self._registry.unregister(name)

    # ------------------------------------------------------------------ helpers
    def _notes_store(self) -> NotesStore:
        if self._notes is None:
            self._notes = NotesStore()
        return self._notes

    def _username(self) -> str | None:
        user = user_context.current_user()
        return user.username if user else None

    def _announce(self, text: str) -> None:
        if self._event_bus is not None:
            self._event_bus.publish_sync(Event(name="system_message", payload={"text": text}, source="jarvis"))

    # ------------------------------------------------------------------ handlers
    def _time(self, params: dict[str, str]) -> str:
        now = datetime.now()
        return f"Agora são {now:%H:%M}."

    def _date(self, params: dict[str, str]) -> str:
        now = datetime.now()
        return f"Hoje é {WEEKDAYS[now.weekday()]}, {now.day} de {MONTHS[now.month - 1]} de {now.year}."

    def _calculate(self, params: dict[str, str]) -> str:
        return f"Dá {calculate(params['expressao'])}."

    def _timer(self, params: dict[str, str]) -> str:
        amount = parse_number(params.get("quantidade"))
        unit = (params.get("unidade") or "minuto").rstrip("s")
        if amount is None or amount <= 0 or unit not in UNIT_SECONDS:
            raise ValueError("Diga quanto tempo, por exemplo: 'me lembra em 10 minutos de tirar o bolo'.")
        seconds = amount * UNIT_SECONDS[unit]
        if seconds > MAX_TIMER_SECONDS:
            raise ValueError("Consigo agendar lembretes de até 24 horas.")
        message = params.get("mensagem") or "o tempo acabou"
        due = datetime.now() + timedelta(seconds=seconds)

        def fire() -> None:
            with self._timers_lock:
                self._timers[:] = [entry for entry in self._timers if entry[2] is not timer]
            _beep()
            self._announce(f"⏰ Lembrete: {message}.")

        timer = threading.Timer(seconds, fire)
        timer.daemon = True
        with self._timers_lock:
            self._timers.append((due, message, timer))
        timer.start()
        unit_label = unit + ("s" if amount != 1 else "")
        return f"Combinado. Te aviso em {amount} {unit_label} ({due:%H:%M}): {message}."

    def _list_timers(self, params: dict[str, str]) -> str:
        with self._timers_lock:
            pending = sorted(self._timers, key=lambda entry: entry[0])
        if not pending:
            return "Você não tem lembretes ativos."
        items = "; ".join(f"{due:%H:%M} — {message}" for due, message, _ in pending)
        return f"Lembretes ativos: {items}."

    def _cancel_timers(self, params: dict[str, str]) -> str:
        with self._timers_lock:
            count = len(self._timers)
            for _, _, timer in self._timers:
                timer.cancel()
            self._timers.clear()
        return f"Cancelei {count} lembrete(s)." if count else "Não havia lembretes ativos."

    def _add_note(self, params: dict[str, str]) -> str:
        text = params["texto"].strip()
        if not text:
            raise ValueError("O que devo anotar?")
        self._notes_store().add(text, self._username())
        return f"Anotado: {text}."

    def _list_notes(self, params: dict[str, str]) -> str:
        notes = self._notes_store().list(self._username())
        if not notes:
            return "Você não tem notas."
        return "Suas notas: " + "; ".join(f"{index}. {note.text}" for index, note in enumerate(reversed(notes), 1)) + "."

    def _clear_notes(self, params: dict[str, str]) -> str:
        removed = self._notes_store().clear(self._username())
        return f"Apaguei {removed} nota(s)."

    def _who_am_i(self, params: dict[str, str]) -> str:
        user = user_context.current_user()
        if user is None:
            return "Ainda não sei quem você é. Crie um usuário com: python main.py --criar-usuario seu_nome"
        role = "administrador" if user.is_admin else "usuário"
        return f"Você é {user.display_name} (login {user.username}, {role})."

    def _rename(self, params: dict[str, str]) -> str:
        user = user_context.current_user()
        if user is None or self._users is None:
            return "Preciso de um usuário ativo para guardar seu nome. Use: python main.py --criar-usuario seu_nome"
        updated = self._users.set_display_name(user.username, params["nome"].strip().title())
        user_context.set_current_user(updated)
        return f"Combinado, vou te chamar de {updated.display_name}."

    def _help(self, params: dict[str, str]) -> str:
        return self._registry.help_text() + " E para qualquer outra coisa, é só pedir em linguagem natural."

    def _greet(self, params: dict[str, str]) -> str:
        name = user_context.display_name()
        greeting = _greeting_for_hour(datetime.now().hour)
        return f"{greeting}{', ' + name if name else ''}! Em que posso ajudar?"

    # ------------------------------------------------------------------ skills
    def _build_skills(self) -> list[Skill]:
        units = r"(?P<unidade>segundos?|minutos?|horas?)"
        return [
            Skill(
                name="conversa.saudacao",
                description="Cumprimenta o usuário.",
                patterns=[
                    r"(?:ola|oi|opa|e ai|eai|hey|fala|salve|bom dia|boa tarde|boa noite)(?:\s+jarvis)?(?:\s+tudo bem)?(?:\s+com voce)?",
                    r"jarvis",
                ],
                handler=self._greet,
                examples=["olá"],
                category="conversa",
            ),
            Skill(
                name="conversa.ajuda",
                description="Lista exemplos do que o JARVIS sabe fazer.",
                patterns=[
                    r"ajuda|socorro|me ajuda|comandos|lista de comandos",
                    r"(?:o\s+)?que\s+(?:mais\s+)?(?:voce\s+)?(?:sabe|pode|consegue)\s+fazer",
                    r"quais\s+(?:sao\s+)?(?:os\s+)?(?:seus\s+)?comandos",
                ],
                handler=self._help,
                examples=["o que você sabe fazer"],
                category="conversa",
            ),
            Skill(
                name="tempo.hora",
                description="Diz a hora atual.",
                patterns=[r"(?:.*\s)?(?:que\s+horas|horas\s+sao|hora\s+e\s+agora|qual\s+(?:e\s+)?a\s+hora|hora\s+certa)(?:\s.*)?"],
                handler=self._time,
                examples=["que horas são"],
                category="tempo",
            ),
            Skill(
                name="tempo.data",
                description="Diz a data e o dia da semana de hoje.",
                patterns=[
                    r"(?:.*\s)?(?:que\s+dia\s+(?:e\s+)?hoje|qual\s+(?:e\s+)?a\s+data|data\s+de\s+hoje|hoje\s+e\s+que\s+dia|que\s+dia\s+da\s+semana)(?:\s.*)?"
                ],
                handler=self._date,
                examples=["que dia é hoje"],
                category="tempo",
            ),
            Skill(
                name="calculadora",
                description="Resolve contas: soma, subtração, multiplicação, divisão, potência e porcentagem.",
                patterns=[r"(?:quanto\s+(?:e|da|e que da)|calcula|calcular|calcule|faz a conta|faca a conta)\s+(?P<expressao>.+)"],
                parameters={"expressao": "A conta, ex.: '15 vezes 3' ou '20% de 150'"},
                required=["expressao"],
                handler=self._calculate,
                examples=["quanto é 15 vezes 3"],
                category="tempo",
            ),
            Skill(
                name="lembrete.criar",
                description="Cria um lembrete/temporizador que avisa depois de alguns segundos, minutos ou horas.",
                patterns=[
                    rf"(?:me\s+)?(?:lembra|lembre|lembrar|avisa|avise|avisar)(?:-me|\s+me)?\s+(?:em|daqui a|daqui|dentro de)\s+(?P<quantidade>{N})\s+{units}(?:\s+(?:de|para|que|pra|sobre)\s+(?P<mensagem>.+))?",
                    rf"(?:cria|criar|crie|coloca|colocar|coloque|liga|ligar|inicia|iniciar|define|definir|faz|bota)?\s*(?:um\s+)?(?:timer|temporizador|cronometro|alarme)\s+(?:de|para|pra|em)\s+(?P<quantidade>{N})\s+{units}(?:\s+(?:para|pra|de)\s+(?P<mensagem>.+))?",
                ],
                parameters={
                    "quantidade": "Número de unidades de tempo",
                    "unidade": "segundos, minutos ou horas",
                    "mensagem": "Do que lembrar (opcional)",
                },
                required=["quantidade", "unidade"],
                raw_params=["mensagem"],
                handler=self._timer,
                permission="notes.write",
                examples=["me lembra em 10 minutos de tirar o bolo"],
                category="lembretes",
            ),
            Skill(
                name="lembrete.listar",
                description="Lista os lembretes ativos.",
                patterns=[r"(?:quais\s+(?:sao\s+)?(?:os\s+)?(?:meus\s+)?|lista(?:r)?\s+(?:os\s+)?(?:meus\s+)?|meus\s+)(?:lembretes|timers|alarmes)(?:\s+ativos)?"],
                handler=self._list_timers,
                permission="notes.read",
                examples=["quais são meus lembretes"],
                category="lembretes",
            ),
            Skill(
                name="lembrete.cancelar",
                description="Cancela todos os lembretes ativos.",
                patterns=[r"(?:cancela|cancelar|cancele|apaga|apagar|para|parar)\s+(?:os\s+|o\s+|todos os\s+)?(?:lembretes?|timers?|alarmes?|temporizador(?:es)?)"],
                handler=self._cancel_timers,
                permission="notes.write",
                examples=["cancelar lembretes"],
                category="lembretes",
            ),
            Skill(
                name="notas.anotar",
                description="Salva uma nota rápida.",
                patterns=[r"(?:anota|anotar|anote|toma nota|tome nota|salva uma nota|cria uma nota|nota)(?:\s+(?:que|ai|isso|isto))?[:\s]+(?P<texto>.+)"],
                parameters={"texto": "Conteúdo da nota"},
                required=["texto"],
                raw_params=["texto"],
                handler=self._add_note,
                permission="notes.write",
                examples=["anota comprar pão"],
                category="notas",
            ),
            Skill(
                name="notas.ler",
                description="Lê as notas salvas.",
                patterns=[r"(?:le|ler|leia|mostra|mostrar|mostre|quais\s+(?:sao\s+)?)?\s*(?:as\s+)?(?:minhas\s+)?(?:notas|anotacoes)"],
                handler=self._list_notes,
                permission="notes.read",
                examples=["ler minhas notas"],
                category="notas",
            ),
            Skill(
                name="notas.apagar",
                description="Apaga todas as notas do usuário.",
                patterns=[r"(?:apaga|apagar|apague|limpa|limpar|limpe|deleta|deletar)\s+(?:todas\s+)?(?:as\s+)?(?:minhas\s+)?(?:notas|anotacoes)"],
                handler=self._clear_notes,
                permission="notes.clear",
                confirm_key="notes.clear",
                confirm_text="Apagar todas as suas notas",
                examples=["apagar minhas notas"],
                category="notas",
            ),
            Skill(
                name="usuario.quem_sou_eu",
                description="Diz qual usuário está usando o JARVIS.",
                patterns=[r"quem\s+sou\s+eu|qual\s+(?:e\s+)?(?:o\s+)?meu\s+(?:nome|usuario|login)|(?:voce\s+)?sabe\s+(?:quem\s+eu\s+sou|meu\s+nome)"],
                handler=self._who_am_i,
                examples=["quem sou eu"],
                category="usuário",
            ),
            Skill(
                name="usuario.renomear",
                description="Muda o nome pelo qual o JARVIS chama o usuário.",
                parameters={"nome": "Como o usuário quer ser chamado"},
                required=["nome"],
                matcher=_match_rename,
                raw_params=["nome"],
                handler=self._rename,
                examples=["me chama de chefe"],
                category="usuário",
            ),
        ]


def _match_rename(normalized: str) -> dict[str, str] | None:
    found = re.fullmatch(
        r"(?:me\s+chama|me\s+chame|pode\s+me\s+chamar|me\s+chamar)\s+de\s+(?P<nome>.+)|meu\s+nome\s+e\s+(?P<nome2>.+)",
        normalized,
    )
    if not found:
        return None
    return {"nome": (found["nome"] or found["nome2"]).strip()}


def _beep() -> None:
    try:
        import winsound

        for _ in range(3):
            winsound.Beep(988, 180)
    except Exception:
        pass
