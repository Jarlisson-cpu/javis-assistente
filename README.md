# JARVIS — Assistente de IA Pessoal

Assistente de IA modular para Windows, inspirado no JARVIS da Marvel: controle por
voz, automação do sistema, memória de longo prazo, múltiplos modelos de IA e
agentes especializados.

> **Fases 0-9 têm uma implementação básica utilizável.** As fases 8 e 9 cobrem
> browser/OCR/comunicação/mídia locais, permissões, bearer/TLS e hardening HTTP.
> Integrações remotas e revisão de produção continuam como trabalho avançado.

## Requisitos

- Python 3.13+ conforme `pyproject.toml`
- Windows (necessário a partir da Fase 6, para os módulos de automação/sistema)
- Microfone e modelo acústico Vosk em português para usar `--voice`
- Chromium do Playwright para `ler site`; Tesseract OCR e idioma `por` para `ler imagem`

## Instalação

```bash
python -m venv .venv
.venv\Scripts\activate        # Windows
pip install -r requirements.txt
copy .env.example .env        # depois preencha suas chaves de API
python -m playwright install chromium
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

- Rodar interface web: `python main.py --web` (abra `http://127.0.0.1:8000`). Para
  bind externo, configure `JARVIS_TLS_CERTFILE`, `JARVIS_TLS_KEYFILE` e
  `JARVIS_WEB_TOKEN` (mínimo de 32 caracteres). Gere um token com
  `python -c "import secrets; print(secrets.token_urlsafe(32))"` e inicie, por
  exemplo, `python main.py --web --host 0.0.0.0`. O dashboard pede o bearer token
  e o guarda apenas na sessão atual. TLS e token não substituem revisão de
  autorização/implantação; não exponha a API a redes não confiáveis.
- TTS: o `VoiceManager` usa `pyttsx3` quando disponível. Sem ele, as respostas
  continuam no histórico/log, sem reprodução de áudio.
- STT offline: instale os pacotes de `requirements.txt`, baixe um modelo Vosk
  compatível com português em https://alphacephei.com/vosk/models e extraia-o em `models/vosk` (ou ajuste
  `voice.stt_model_path` em `config.yaml`). Inicie com `python main.py --voice`
  e diga “Jarvis” antes do comando. O microfone só é aberto nesse modo explícito.
- A palavra de ativação é configurável em `voice.wake_word`; taxa de amostragem
  em `voice.stt_sample_rate`.

- Plugins disponíveis:
  - `abrir <aplicativo>` — abre o aplicativo ou executa um binário do PATH.
  - `buscar <termo>` — abre uma busca no navegador padrão.
  - `ler site <URL>` — extrai texto de páginas públicas via Playwright; endereços
    locais e IPs privados são bloqueados.
  - `ler imagem <caminho>` — extrai texto de imagens usando OCR local; requer
    Tesseract instalado no sistema e idioma português.
  - `rascunho email <destinatário> | <assunto> | <mensagem>` — abre o rascunho
    no cliente de e-mail; o JARVIS não envia a mensagem.
  - `buscar música <termo>` e `buscar vídeo <termo>` — abrem pesquisas no YouTube.
  - `pausar mídia`, `tocar mídia`, `próxima música`, `música anterior`,
    `aumentar volume` e `diminuir volume` — enviam teclas de mídia do Windows.
  - `planejar <objetivo>`, `revisar <texto>` e `explicar <assunto>` — acionam
    instruções especializadas pelo provedor de IA configurado.
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
| 2 | Memória (SQLite + ChromaDB) | ✅ |
| 3 | IA multi-modelo | ✅ |
| 4 | Voz (STT local Vosk, TTS, palavra de ativação no modo terminal) | ✅ |
| 5 | Interface (GUI Tkinter e dashboard web) | ✅ |
| 6 | Sistema / Automação / Arquivos básicos com permissões e confirmação | ✅ |
| 7 | Agentes especializados (planejamento, revisão e explicação) | ✅ Básico |
| 8 | Browser público, OCR local, rascunho de e-mail, busca de mídia e controles de reprodução do Windows | ✅ Básico |
| 9 | Bearer + TLS remoto, validação de entradas, limites, proteção de caminhos, confirmação e testes | ✅ Básico |

O escopo básico não envia e-mails nem integra Telegram/Discord; não faz varredura
antimalware/firewall, e a API ainda não tem contas ou roles de usuário. A exposição
remota requer revisão de identidade, autorização e configuração operacional antes
de uso em produção.

Veja [ARCHITECTURE.md](ARCHITECTURE.md) para as decisões de design.
