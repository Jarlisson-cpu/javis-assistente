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
| `voice/` | wake word, STT, TTS, streaming | 4 |
| `gui/` | dashboard futurista | 5 |
| `automation/`, `system/`, `terminal/` | controle do Windows, mouse/teclado, shell | 6 |
| `skills/` | comandos de alto nível expostos ao usuário | 6+ |
| `vision/` | OCR, leitura de tela, reconhecimento de imagem | 8 |
| `browser/` | automação de navegador (Playwright) | 8 |
| `security/` | malware, firewall, cofre de arquivos | 8 |
| `plugins/` | extensões de terceiros/pessoais | contínuo |
| `utils/` | utilitários compartilhados | contínuo |
| `logs/` | saída do logging (não é código) | — |

## Por que GUI, TTS e provedor de IA ficaram em aberto

Essas três escolhas **não bloqueiam** o núcleo: cada uma vira uma implementação
isolada atrás de uma interface (`ConfirmationProvider` hoje; `AIProvider` e
`TTSEngine` nas Fases 3-4), conectada via `event_bus` e `config.yaml`. Dá para
trocar PySide6 por uma interface web, ou TTS offline por nuvem, sem tocar no
núcleo. As decisões concretas ficam para as Fases 3, 4 e 5 — o núcleo entregue
aqui já funciona e é testado independentemente delas.

## Fluxo de eventos (visão geral, a partir da Fase 4+)

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
        event_bus.publish("jarvis_response")
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
