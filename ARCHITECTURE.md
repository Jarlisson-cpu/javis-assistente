# Arquitetura do JARVIS

## Princípios

- **Baixo acoplamento**: módulos (`voice`, `ai`, `gui`, `automation`...) nunca se
  importam diretamente. Toda comunicação passa pelo `core.event_bus`.
- **Inversão de dependência**: o núcleo (`core`) não conhece PyQt, Whisper,
  Anthropic ou qualquer biblioteca específica — essas escolhas ficam isoladas em
  cada módulo, atrás de interfaces.
- **Plugins por convenção**: qualquer pasta em `plugins/` com uma classe `Plugin`
  é carregada automaticamente, sem registro manual.
- **Segurança por padrão**: ações destrutivas passam pelo
  `core.confirmation.ConfirmationGate` antes de executar, configurável em
  `config.yaml → security.require_confirmation_for`.

## Módulos

| Pasta | Responsabilidade | Fase |
|---|---|---|
| `core/` | config, logging, event bus, plugins, confirmação | 0-1 |
| `config/` | schema de configuração (Pydantic) | 0 |
| `database/` | SQLite + armazenamento vetorial | 2 |
| `memory/` | memória de curto/longo prazo sobre `database/` | 2 |
| `ai/` | abstração multi-modelo e roteamento por tarefa | 3 |
| `plugins/specialized_agents/` | agentes de planejamento, revisão e explicação via AIManager | 7 |
| `voice/` | STT local Vosk, TTS pyttsx3, palavra de ativação no modo terminal | 4 |
| `gui/`, `web/` | GUI Tkinter e dashboard web | 5 |
| `automation/`, plugins | automação básica do Windows, mouse/teclado e arquivos com permissões | 6 |
| `communication/`, `media/` | rascunho de e-mail local, busca de mídia e teclas de controle do Windows | 8 |
| `skills/` | comandos de alto nível expostos ao usuário | 6+ |
| `vision/` | OCR local de arquivos de imagem (Pillow + Tesseract) | 8 |
| `browser/` | leitura de páginas públicas via Playwright com bloqueio de destinos locais | 8 |
| `security/` | permissões, confirmação destrutiva, autenticação bearer e proteções HTTP | 6, 9 |
| `plugins/` | extensões de terceiros/pessoais | contínuo |
| `utils/` | utilitários compartilhados | contínuo |
| `logs/` | saída do logging (não é código) | — |

## Decisões de implementação

Os módulos ficam desacoplados atrás de interfaces e configuração. O STT usa
Vosk local, o TTS usa pyttsx3 e o modo de voz é ativado explicitamente com
`--voice`; a palavra de ativação é reconhecida no áudio capturado, sem detecção
contínua em hardware dedicado. A GUI desktop usa Tkinter, e também há dashboard
web. Trocar essas escolhas não exige acoplar os módulos ao núcleo.

O servidor web atende apenas o loopback por padrão. `JARVIS_WEB_TOKEN` protege os
endpoints API via bearer; hosts externos exigem token com ao menos 32 caracteres
e certificado TLS via `JARVIS_TLS_CERTFILE` e `JARVIS_TLS_KEYFILE`. O dashboard
solicita o token e o guarda em `sessionStorage`. Isso não implementa identidade
de usuário ou roles; limites de entrada e TLS não substituem revisão de acesso
para produção.

## Fluxo de eventos

```
voz/texto do usuário
        │
        ▼
   event_bus.publish("user_message")
        │
        ├──► ai/          (decide o que fazer, qual modelo usar)
        ├──► memory/      (registra contexto)
        └──► automation/  (executa a ação, passando por confirmation.py se destrutiva)
                │
                ▼
              event_bus.publish("system_message")
                │
                ├──► voice/  (fala a resposta)
                └──► gui/    (atualiza o dashboard)
```

## Convenção para novos plugins

1. Crie uma pasta em `plugins/meu_plugin/`.
2. Implemente uma classe que herde de `core.plugin_loader.Plugin`, com `name`,
   `version`, `description` e o método `setup(event_bus)`.
3. Pronto — é carregada automaticamente no próximo `python main.py` (a menos que
   esteja em `plugins.disabled` no `config.yaml`).

Veja `plugins/example_greeting/` como modelo.
