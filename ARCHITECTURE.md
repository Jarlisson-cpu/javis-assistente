# Arquitetura do JARVIS

## Princípios

- **Baixo acoplamento**: módulos (`voice`, `ai`, `gui`, `system`...) não se
  importam diretamente para conversar; a comunicação passa pelo `core.event_bus`.
- **Uma definição, três usos**: cada comando é uma `Skill` registrada uma vez em
  `skills.registry` e funciona por texto, por voz e como ferramenta do agente de IA.
- **Segurança por padrão**: toda skill declara a permissão que exige; as
  destrutivas declaram uma chave de confirmação. O `SkillExecutor` aplica as duas
  regras antes de executar — não há caminho que pule a checagem.
- **Plugins por convenção**: qualquer pasta em `plugins/` com uma classe `Plugin`
  é carregada automaticamente.

## Módulos

| Pasta | Responsabilidade |
|---|---|
| `core/` | config, logging, event bus (com isolamento de falhas), plugins, confirmação, normalização de texto (`text.py`) |
| `config/` | schema Pydantic de `config.yaml` |
| `skills/` | `Skill`, `SkillRegistry`, `SkillExecutor` (permissão + confirmação) e `SkillRouter` |
| `system/` | `SystemController`: volume, brilho, energia, janelas, teclado, apps, status, tema, clipboard, pastas, terminal |
| `users/` | contas (PBKDF2), sessões web e usuário ativo da sessão local |
| `voice/` | `VoiceManager` (STT Vosk/Google, TTS pyttsx3/Windows) e `VoiceAssistant` (palavra de ativação, modo conversa, confirmação falada) |
| `ai/` | provedores Claude, OpenAI, Gemini e offline; laço de tool use |
| `memory/` | histórico SQLite (por usuário), notas e memória vetorial opcional (ChromaDB) |
| `security/` | registro de permissões (com padrões) e gerenciador persistente |
| `gui/`, `web/` | app Tkinter e painel web (login, confirmações, microfone do navegador) |
| `browser/`, `vision/`, `communication/`, `media/` | leitura de sites, OCR, rascunho de e-mail, busca e teclas de mídia |
| `plugins/` | `notebook_control`, `productivity`, `open_app_action`, `search_web`, `chat_ai`, agentes e outros |

## Fluxo de uma mensagem

```
voz (VoiceAssistant) / terminal / GUI / web
        │  event_bus.publish("user_message")
        ▼
 1. memória grava a mensagem (com o usuário)
 2. SkillRouter: o texto normalizado casa com alguma Skill?
        └─ sim → SkillExecutor (permissão → confirmação → handler) → "system_message"
 3. plugins legados por prefixo (abrir, buscar, ler site...) — ignoram o que já é skill
 4. chat_ai: não é comando?
        ├─ Claude/OpenAI → agente com todas as skills como ferramentas (passam pelo mesmo SkillExecutor)
        ├─ Gemini → resposta em texto
        └─ offline → resposta local + "você quis dizer ...?"
        ▼
 "system_message" → memória, voz (TTS), terminal, GUI, web
```

## Como criar um comando novo

```python
from core.plugin_loader import Plugin
from skills import Skill, registry


class MeuPlugin(Plugin):
    name = "meu_plugin"

    def setup(self, event_bus):
        registry.register(
            Skill(
                name="cafe.pedir",
                description="Abre o site da cafeteria.",          # o agente de IA lê isto
                patterns=[r"(?:quero|pede) (?:um )?cafe(?: (?P<tipo>.+))?"],  # texto normalizado
                parameters={"tipo": "Tipo de café (opcional)"},
                handler=lambda p: f"Pedindo um café {p.get('tipo', 'coado')}.",
                permission="automation.open_app",
                examples=["quero um café expresso"],
                category="diversos",
            )
        )
```

Os padrões casam contra o texto **normalizado** (minúsculo, sem acentos, sem
pontuação, sem "por favor"/"Jarvis"). Use `raw_params` para recuperar o trecho
original com maiúsculas e acentos (ex.: texto a digitar). Plugins que precisam
do núcleo (banco, usuários) implementam `attach_core(core)`.

## Decisões

- **Teclas virtuais para volume** (2% por tecla) em vez de APIs COM: funcionam
  em qualquer Windows sem dependências extras.
- **Brilho via WMI**: funciona em telas internas de notebooks; monitores externos
  geralmente não aceitam, e o JARVIS avisa.
- **Fechar apps com `taskkill` sem `/F`**: o app recebe um pedido normal de
  fechamento e pode perguntar se você quer salvar.
- **TTS numa thread dedicada**: o SAPI/pyttsx3 não é thread-safe; uma fila
  serializa as falas e o modo voz espera a fala terminar antes de ouvir de novo.
- **Claude com `fallbacks: "default"`**: se o modelo principal recusar por
  política, a própria API refaz o pedido com um modelo alternativo.
