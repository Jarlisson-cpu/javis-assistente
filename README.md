# JARVIS — Assistente de IA Pessoal

Assistente de IA modular para Windows, inspirado no JARVIS da Marvel: controle por
voz, automação do sistema, memória de longo prazo, múltiplos modelos de IA e
agentes especializados.

> **Fase atual: 0/1 — Núcleo.** Ainda não há voz, interface gráfica ou automação de
> sistema — veja o roadmap abaixo. O projeto é construído em fases pequenas e
> testáveis, nunca de uma vez só.

## Requisitos

- Python 3.13+ (desenvolvido/testado aqui com 3.12 — nenhuma sintaxe exclusiva de
  3.13 foi usada, mas rode com 3.13 no seu ambiente final)
- Windows (necessário a partir da Fase 6, para os módulos de automação/sistema)

## Instalação

```bash
python -m venv .venv
.venv\Scripts\activate        # Windows
pip install -r requirements.txt
copy .env.example .env        # depois preencha suas chaves de API
```

## Executar

```bash
python main.py
```

## GUI e Voz (opcionais)

- Rodar GUI (Tkinter):

```bash
python main.py --gui
```

- TTS: O projeto inclui um `VoiceManager` que usa `pyttsx3` se disponível. Sem `pyttsx3` o TTS apenas fará log das frases.

- Plugins disponíveis:
  - `abrir <aplicativo>` — abre o aplicativo ou executa um binário do PATH.
  - `buscar <termo>` — abre uma busca no navegador padrão.
  - `ler arquivo <caminho>` — lê o conteúdo de um arquivo dentro do diretório do projeto.
  - `criar arquivo <caminho> : <texto>` — cria ou atualiza um arquivo com o conteúdo especificado.
  - `apagar arquivo <caminho>` — apaga um arquivo dentro do projeto.

## Empacotamento / Atalho Windows

Um script PowerShell `scripts/create_shortcut.ps1` cria um atalho na área de trabalho que executa o `main.py --gui` usando o `python` da virtualenv do projeto.

```powershell
.\scripts\create_shortcut.ps1
```


## Testar

```bash
pytest
```

## Roadmap

| Fase | Entrega | Status |
|---|---|---|
| 0 | Arquitetura, config, estrutura de pastas | ✅ |
| 1 | Núcleo: logging, plugins, event bus, confirmação | ✅ |
| 2 | Memória (SQLite + ChromaDB) | ⏳ |
| 3 | IA multi-modelo | ⏳ |
| 4 | Voz (wake word, STT, TTS) | ⏳ |
| 5 | Interface (dashboard) | ⏳ |
| 6 | Sistema / Automação / Arquivos | ⏳ |
| 7 | Agentes especializados | ⏳ |
| 8 | Integrações (navegador, comunicação, mídia, segurança) | ⏳ |
| 9 | Hardening e testes finais | ⏳ |

Veja [ARCHITECTURE.md](ARCHITECTURE.md) para as decisões de design.
