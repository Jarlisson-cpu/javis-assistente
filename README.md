# JARVIS — Assistente Pessoal por Voz para Windows

Assistente pessoal inspirado no JARVIS da Marvel: você fala (ou digita) e ele
**executa no notebook** — volume, brilho, músicas, janelas, apps, sites, prints,
lembretes, notas, energia, terminal — e conversa sobre qualquer assunto com IA
(Claude, GPT ou Gemini). Tem **usuários com senha**, permissões por ação e
confirmação obrigatória para tudo que é destrutivo.

```text
você> Jarvis, coloca o volume em 30 e tira um print
jarvis> Volume ajustado para 30%.
jarvis> Print salvo em C:\Users\voce\Pictures\Jarvis\print_2026-10-27_10-21-05.png.
você> me lembra em 10 minutos de tirar o bolo do forno
jarvis> Combinado. Te aviso em 10 minutos (10:31): tirar o bolo do forno.
você> desliga o computador em 30 minutos
jarvis> Confirma: Desligar o computador em 30 minuto(s)? Diga sim ou não.
```

## Instalação

Requer Windows 10/11 e Python 3.13+.

```bash
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
copy .env.example .env
```

No `.env`, coloque **uma** chave de IA (opcional, mas é ela que permite pedidos
livres como "deixa o som mais baixo e me lembra da reunião em 15 minutos"):

| Variável | Provedor | Observação |
|---|---|---|
| `ANTHROPIC_API_KEY` | Claude (`claude-opus-5-5`) | recomendado: executa ações com ferramentas |
| `OPENAI_API_KEY` | GPT (`gpt-4o-mini`) | executa ações com ferramentas |
| `GOOGLE_API_KEY` | Gemini | só conversa (não aciona ferramentas) |

Sem chave, todos os comandos diretos funcionam e o JARVIS sugere o comando mais
parecido quando não entende ("Você quis dizer 'aumentar o volume'?").

## Primeiro uso: crie seu usuário

```bash
python main.py --criar-usuario joao          # pede o nome de exibição e a senha
python main.py --usuarios                    # lista usuários
python main.py --trocar-senha joao
python main.py --remover-usuario joao
```

O primeiro usuário vira **administrador**. No terminal, na voz e na GUI o
JARVIS usa automaticamente o único usuário (ou o primeiro admin) — use
`--usuario nome` para escolher outro. Na interface web, com usuários
cadastrados, é obrigatório fazer login. Senhas são guardadas com PBKDF2-SHA256
e sal individual; sessões web expiram (12 h por padrão) e o login tem limite de
tentativas.

## Modos de uso

```bash
python main.py --voice     # controle total por voz: "Jarvis, ..."
python main.py             # conversa por texto no terminal
python main.py --gui       # app desktop (com botão de microfone)
python main.py --web       # painel em http://127.0.0.1:8000 (microfone no navegador)
```

Para o JARVIS de voz subir sozinho quando o Windows ligar:

```powershell
.\scripts\create_shortcut.ps1 -IniciarComWindows
```

## Voz

- **Palavra de ativação:** diga "Jarvis" + o pedido, ou só "Jarvis" e espere o
  bipe. Variações comuns do reconhecimento ("Jarbas", "Javis") também valem.
- **Modo conversa:** depois de um pedido, por 25 s você pode emendar outro sem
  repetir "Jarvis". "Pode dormir" encerra a conversa; "encerrar assistente" sai.
- **"Para"/"chega"** interrompe a fala do JARVIS.
- **Confirmação falada:** ações destrutivas perguntam "Confirma...? Diga sim ou não".
- **Reconhecimento (STT):** `voice.stt_engine: auto` usa o **Vosk** (offline,
  o áudio não sai do PC) se houver modelo instalado; senão usa o Google (mais
  preciso, mas envia o áudio da frase). Para instalar o modelo offline:

  ```bash
  python scripts/baixar_modelo_vosk.py            # ~31 MB
  python scripts/baixar_modelo_vosk.py --grande   # ~1,6 GB, mais preciso
  ```

- **Fala (TTS):** pyttsx3 com voz em português (ou a voz nativa do Windows).
  Instale a voz "Português (Brasil)" em *Configurações > Hora e idioma > Fala*
  se o JARVIS falar com sotaque inglês.

## O que ele sabe fazer

Diga "ajuda" ou abra "O que sei fazer" no painel web para a lista completa.

| Área | Exemplos |
|---|---|
| Som e mídia | "volume em 50", "aumenta o volume em 20", "muta o som", "pausa a música", "próxima música", "toca Legião Urbana" |
| Tela | "brilho em 70", "deixa a tela mais escura", "ativa o modo escuro", "tira um print" |
| Energia | "bloqueia a tela", "suspende o computador", "desliga o computador em 30 minutos", "reinicia o notebook", "cancela o desligamento" |
| Janelas e teclado | "copia", "cola", "nova aba", "fecha essa aba", "minimiza tudo", "troca de janela", "aperta enter", "digita Bom dia a todos", "desce a página" |
| Apps e sites | "abre o Spotify", "abrir YouTube", "abre as configurações de bluetooth", "abre a pasta downloads", "fecha o Chrome" |
| Informações | "como está a bateria", "status do sistema", "quanto espaço livre", "estou conectado", "o que está pesando o computador", "o que eu copiei" |
| Produtividade | "que horas são", "que dia é hoje", "quanto é 15 vezes 3", "20% de 150", "me lembra em 10 minutos de...", "timer de 5 minutos", "anota comprar pão", "ler minhas notas" |
| Web | "pesquisa receita de bolo", "buscar música Coldplay", "ler site https://...", "ler imagem C:\\print.png" |
| Arquivos | "cria uma pasta chamada Projetos na área de trabalho", "criar arquivo nota.txt : texto", "ler arquivo nota.txt" |
| Usuário | "quem sou eu", "me chama de chefe" |
| Terminal | "executa o comando ipconfig" — desligado por padrão; ative a permissão `terminal.run` (sempre pede confirmação) |
| Agentes | "planejar ...", "revisar ...", "explicar ..." |

Com Claude ou OpenAI configurados, **qualquer pedido em linguagem natural**
vira ações: o agente de IA recebe todas as skills acima como ferramentas.

## Segurança

- **Permissões** por ação (GUI, painel web ou `config.yaml → security.permissions`).
  Alterações feitas pela interface ficam em `data/permissions.json`.
  Com usuários cadastrados, só administradores mudam permissões.
- **Confirmação obrigatória** (voz, terminal, GUI ou navegador) para desligar,
  reiniciar, suspender, apagar arquivos/notas e executar comandos no terminal —
  lista em `security.require_confirmation_for`.
- **Fechar apps** pede ao Windows para fechar normalmente (sem forçar), então o
  app ainda oferece "salvar alterações".
- **Painel web** atende só `127.0.0.1` por padrão. Para expor na rede, configure
  TLS (`JARVIS_TLS_CERTFILE`/`JARVIS_TLS_KEYFILE`) e `JARVIS_WEB_TOKEN` (32+ caracteres).

## Testes

```bash
pytest
```

## Estrutura

Veja [ARCHITECTURE.md](ARCHITECTURE.md).
