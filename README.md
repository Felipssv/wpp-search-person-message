# WhatsApp Search Person Message 🔍💬

Script em Python com **Playwright** que acessa o WhatsApp Web, navega até um **grupo específico** e filtra todas as mensagens enviadas por uma **pessoa específica** (buscando tanto pelo **nome** quanto pelo **número de telefone**).

---

## 🚀 Funcionalidades

- **Busca por Nome ou Número**:
  - Encontra pelo nome ou parte do nome (ex: `"Lucas"` encontra `"Lucas Silva"`).
  - Encontra pelo número de telefone, independentemente da formatação (ex: `"99999-8888"`, `"11999998888"` ou `"+55 11 99999-8888"`).
- **Reutilização Inteligente de Sessão (CDP - Porta 9222)**:
  - Se você já tiver o WhatsApp Web aberto com depuração remota ativada, o script conecta instantaneamente na mesma aba sem abrir novas janelas.
  - Se não houver nenhum aberto, ele cria uma instância independente e **não a fecha**, permitindo que você a reutilize nas próximas buscas.
- **Sessão Persistente (Login Único)**:
  - Salva a autenticação na pasta `whatsapp_session/`. Você só precisa escanear o QR Code uma única vez.
- **Rolagem Automática (Histórico Antigo)**:
  - Rola a conversa para cima para carregar mensagens anteriores que não estavam visíveis na tela.
- **Seletores Modernos e Resilientes**:
  - Baseado nos identificadores oficiais do WhatsApp Web (`data-testid="cell-frame-title"`, `data-testid="cell-frame-container"`, `copyable-text` e `data-pre-plain-text`).

---

## 🛠️ Pré-requisitos

- **Python 3.10** ou superior instalado.
- Navegador Google Chrome ou Chromium.

---

## 📦 Instalação

1. **Clone ou abra a pasta do projeto no VS Code**:
   ```powershell
   cd c:\ws-vscode\wpp-person-filter
   ```

2. **Crie e ative o ambiente virtual (venv)**:
   ```powershell
   python -m venv .venv
   .\.venv\Scripts\Activate.ps1
   ```

3. **Instale as dependências**:
   ```powershell
   .\.venv\Scripts\pip install -r requirements.txt
   ```

4. **Instale os binários do navegador para o Playwright**:
   ```powershell
   .\.venv\Scripts\playwright install chromium
   ```

---

## 🏃 Como Rodar

### Modo 1: Execução Padrão (Recomendado)

Basta executar o script com o Python do ambiente virtual:

```powershell
.\.venv\Scripts\python main.py
```

O terminal solicitará:
1. **Nome do Grupo**: Nome exato ou parcial do grupo (ex: `Família`, `Projeto X`).
2. **Pessoa**: Nome ou número de telefone da pessoa que você deseja filtrar.

> **Primeira execução**: Uma janela do navegador será aberta. Escaneie o QR Code com seu celular. Nas próximas execuções, o login já estará salvo e ele reutilizará a janela automaticamente!

---

### Modo 2: Conectar no seu Google Chrome pessoal já aberto

Se você quiser que o script use o Chrome que você já usa no dia a dia com o WhatsApp aberto:

1. Feche as instâncias do Chrome.
2. Abra o Chrome permitindo a conexão na porta `9222`:
   - Pressione `Win + R` e execute:
     ```cmd
     chrome.exe --remote-debugging-port=9222
     ```
3. Abra o WhatsApp Web nessa janela do Chrome.
4. Execute o script:
   ```powershell
   .\.venv\Scripts\python main.py
   ```
5. O script detectará a porta `9222`, encontrará a aba aberta do WhatsApp e fará a busca nela sem abrir nenhuma outra janela e **sem fechá-la ao final**.

---

## 🧠 Como Funciona por Baixo dos Panos

```
[ Início ]
    │
    ▼
Verifica porta 9222 (CDP)
    ├─► Aberta? ──► Conecta à aba existente de web.whatsapp.com
    └─► Fechada? ──► Inicia processo independente com ./whatsapp_session
    │
    ▼
Acessa a barra de pesquisa (#side [role='textbox'] / [data-testid='chat-list-search'])
    │
    ▼
Digita o nome do grupo e clica no resultado ([data-testid='cell-frame-title'])
    │
    ▼
Rola a tela para cima (scroll_count) carregando mensagens antigas no DOM
    │
    ▼
Extrai mensagens via atributo nativo 'data-pre-plain-text' ([Data/Hora] Autor: )
    │
    ▼
Filtra por Nome (case-insensitive) ou Telefone (dígitos normalizados)
    │
    ▼
Exibe as mensagens encontradas no console e mantém o WhatsApp aberto
```

---

## 📂 Estrutura do Projeto

```
wpp-person-filter/
├── .venv/                 # Ambiente virtual Python
├── whatsapp_session/      # Dados de sessão e login (ignorado no git)
├── .gitignore             # Arquivos ignorados pelo Git
├── requirements.txt       # Dependências do projeto (Playwright)
├── main.py                # Código-fonte principal
└── README.md              # Documentação do projeto
```

---

## ⚙️ Parâmetros da Função

Caso queira importar a função em outro script:

```python
from main import search_person_messages

mensagens = search_person_messages(
    group_name="Nome do Grupo",
    person="Nome ou Telefone",
    scroll_count=5,          # Quantidade de vezes para rolar e carregar mensagens antigas
    user_data_dir="./whatsapp_session",
    headless=False,          # True para rodar em segundo plano sem interface gráfica
    port=9222,               # Porta de depuração CDP
    close_browser=False      # False para manter o navegador aberto após a busca
)

for msg in mensagens:
    print(f"[{msg['timestamp']}] {msg['sender']}: {msg['text']}")
```

