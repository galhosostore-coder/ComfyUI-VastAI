# ComfyUI Híbrido: Coolify + Vast.ai + Google Drive

**Simples:** Coloque modelos no Google Drive → Execute workflows → Pronto.

## 🚀 Como Funciona

1. Você cria workflows no **ComfyUI (Coolify)** - leve, sem GPU
2. Coloca os modelos no **Google Drive** 
3. Roda o script → Aluga GPU → Baixa modelos → Gera → Desliga

**Custo fixo: $0/mês** (só paga GPU quando usar)

## 📋 Setup

### 1. Organize seu Google Drive

Crie estas pastas no seu Drive:
```
📁 ComfyUI Models/
├── 📁 checkpoints/   ← Modelos principais (SD, SDXL, Flux)
├── 📁 loras/         ← LoRAs
├── 📁 controlnet/    ← ControlNet
├── 📁 vae/           ← VAEs
├── 📁 upscale_models/← Upscalers
└── 📁 embeddings/    ← Embeddings
```

Compartilhe a pasta principal: **"Qualquer pessoa com o link"**

### 2. Configure no Coolify (Environment Variables)

Adicione estas variáveis na aba **Environment Variables**:

| Variável | Obrigatório | Descrição |
|:---------|:-----------:|:----------|
| `VAST_API_KEY` | ✅ | Sua chave da Vast.ai |
| `GDRIVE_FOLDER_ID` | ✅ | ID da pasta do Drive* |
| `VAST_GPU` | ❌ | GPU (padrão: RTX_3090) |
| `VAST_PRICE` | ❌ | Preço max (padrão: 0.5) |

**\*Como pegar o Folder ID:**
```
Link: https://drive.google.com/drive/folders/1MoYmNNAf7gpYOEuYNrem4bQjXLqj6VY9
                                          ↑↑↑↑↑↑↑↑↑↑↑↑↑↑↑↑↑↑↑↑↑↑↑↑↑↑↑↑↑↑↑
                                          Este é o FOLDER_ID
```

### 🛠️ Configuração Inicial

#### **Windows**
1. Clique duas vezes em `setup.bat`.
2. Digite sua API Key da Vast.ai quando pedir.

#### **Mac / Linux (VPS)**
1. Abra o Terminal na pasta.
2. Rode:
   ```bash
   chmod +x setup.sh
   ./setup.sh
   ```
3. Digite sua API Key quando pedir.

> **Nota:** O script cria um ambiente virtual (`.venv`) automaticamente para não conflitar com seu sistema.

---

### 3. Execute

**No Windows:**
```bash
python vastai_runner.py --workflow examples/simple_txt2img.json
```

**No Mac / Linux:**
```bash
./run.sh --workflow examples/simple_txt2img.json
```

_(O `run.sh` é um atalho criado automaticamente pelo setup que já usa o ambiente virtual)_

### 🐳 Rodando via Docker (Localmente)

Se você preferir rodar tudo isolado via Docker no seu PC:

1. Crie um arquivo `.env` com suas chaves (use o modelo `.env.example`).
2. Rode:
   ```bash
   docker-compose up -d
   ```
3. Acesse: `http://localhost:8188`

As pastas `output`, `input` e `custom_nodes` estarão sincronizadas com seu Windows.

---

### 🔄 Sincronização Automática (Novo!)

O sistema inclui um **Custom Node** chamado `ComfyUI-GDrive-Sync`.

1. Adicione o node **"Google Drive Sync"** no seu workflow (categoria `VastAI`).
2. Clique em "Sync Now" ou apenas rode o workflow.
3. Ele força a atualização da lista de modelos do Google Drive (ignorando o cache de 1h).
4. Novos modelos aparecem no ComfyUI sem precisar reiniciar o container!

> **Cache Inteligente:** Por padrão, o sistema faz cache da lista de arquivos por 1 hora para acelerar o boot. O botão "Sync Now" força a limpeza desse cache. modelos.

Isso serve para que **os nomes dos seus modelos apareçam nos menus do ComfyUI**, mesmo sem ter baixado os arquivos de 10GB.

Isso é automático. Basta ter a variável `GDRIVE_FOLDER_ID` configurada.

```bash
# Rodar workflow
python vastai_runner.py --workflow arquivo.json

# Parar todas as GPUs (para cobrança)
python vastai_runner.py --stop

# Ver ajuda das variáveis
python vastai_runner.py --env-help
```

## ⚙️ Opções

| Opção | Descrição |
|:------|:----------|
| `--gpu RTX_4090` | Escolher GPU específica |
| `--price 1.0` | Preço máximo diferente |
| `--keep-alive` | Não destruir após rodar |

## 🧩 Custom Nodes Extras

Quer usar nodes customizados que não vêm no padrão?

1. Crie um arquivo `custom_nodes.txt` na raiz da sua pasta no Google Drive.
2. Liste os links do GitHub dos nodes que você quer:
   ```text
   https://github.com/ltdrdata/ComfyUI-Manager.git
   https://github.com/cubiq/ComfyUI_IPAdapter_plus.git
   ```
3. O script vai instalar automaticamente antes de iniciar!

## 💰 Custos

| Item | Custo |
|:-----|:------|
| Google Drive | Grátis (15GB) |
| Vast.ai | ~$0.30-1.00/hora |
| **Mensal** | **$0** |

## ⚠️ Importante

1. **Links públicos**: Configure "Qualquer pessoa com o link" no GDrive
2. **Primeira vez demora**: Baixar modelos pode levar alguns minutos
3. **Sempre pare**: O script destrói automaticamente, mas confira!
