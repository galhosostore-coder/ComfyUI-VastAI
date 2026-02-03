# ComfyUI Híbrido: Coolify + Vast.ai

Execute uma instância leve do ComfyUI no Coolify (para criar workflows) e use GPUs da Vast.ai para processamento pesado sob demanda.

## 🚀 Quick Start

### 1. Instale as Dependências (no seu PC)
```bash
pip install vastai requests websocket-client
vastai set api-key SUA_CHAVE_VAST_AI
```

### 2. Configure o Armazenamento de Modelos
```bash
# Primeira vez: cria disco persistente na Vast.ai
python vastai_runner.py --setup-storage --gpu RTX_4090 --disk 50
```

### 3. Adicione seus Modelos
```bash
# Baixar modelo do CivitAI ou HuggingFace
python vastai_runner.py --add-model "https://civitai.com/.../modelo.safetensors"

# Especificar tipo de modelo manualmente
python vastai_runner.py --add-model "URL" --model-type lora
```

### 4. Execute Workflows
```bash
# Rodar um workflow exportado do ComfyUI
python vastai_runner.py --workflow meu_fluxo.json
```

## 📋 Comandos Disponíveis

| Comando | Descrição |
|:--------|:----------|
| `--setup-storage` | Cria disco persistente na Vast.ai |
| `--add-model <URL>` | Baixa modelo para o disco |
| `--remove-model <nome>` | Remove modelo do disco |
| `--list-models` | Lista todos os modelos salvos |
| `--workflow <arquivo>` | Executa workflow no Vast.ai |
| `--stop` | Para todas as instâncias (para cobrança) |

## ⚙️ Opções

| Opção | Padrão | Descrição |
|:------|:-------|:----------|
| `--gpu` | RTX_3090 | GPU para buscar |
| `--price` | 0.5 | Preço máximo $/hora |
| `--disk` | 50 | Tamanho do disco em GB |
| `--keep-alive` | false | Não destruir instância após workflow |

## 🌐 Variáveis de Ambiente (Coolify)

Configure no Coolify para rodar do servidor:

| Variável | Descrição |
|:---------|:----------|
| `VAST_API_KEY` | Sua chave da Vast.ai |
| `VAST_GPU` | GPU preferida (ex: RTX_4090) |
| `VAST_PRICE` | Preço máximo por hora |

## 💾 Sobre o Armazenamento Persistente

- Os modelos são salvos em `/workspace/models/` na Vast.ai
- O disco persiste mesmo após desligar a GPU
- Custo: ~$0.10/GB/mês (50GB = $5/mês)
- Próxima vez que alugar, os modelos já estarão lá!

## 📁 Estrutura dos Modelos

```
/workspace/models/
├── checkpoints/     # Modelos principais (SD, SDXL, Flux)
├── loras/           # LoRAs
├── controlnet/      # ControlNet
├── vae/             # VAEs
├── upscale_models/  # Upscalers (ESRGAN, etc)
├── embeddings/      # Embeddings/Textual Inversion
├── clip/            # CLIP models
└── unet/            # UNet models
```

## ⚠️ Importante

1. **Pare as instâncias** quando terminar para evitar cobranças:
   ```bash
   python vastai_runner.py --stop
   ```

2. O disco persistente tem um custo mensal pequeno mesmo sem GPU rodando.

3. Custom Nodes que precisam de modelos específicos devem ter os modelos adicionados via `--add-model`.

