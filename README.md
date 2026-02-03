# ComfyUI Híbrido: Coolify + Vast.ai + Google Drive

Execute ComfyUI leve no Coolify para criar workflows. Use GPUs da Vast.ai sob demanda. Modelos armazenados no seu Google Drive (custo zero).

## 🚀 Como Funciona

```
┌─────────────────┐     ┌──────────────┐     ┌─────────────────┐
│  Google Drive   │────▶│   Vast.ai    │────▶│  Imagem Gerada  │
│  (seus modelos) │     │  (GPU alugada)│     │  (vast_outputs/)│
└─────────────────┘     └──────────────┘     └─────────────────┘
```

1. Você armazena os modelos no **Google Drive**
2. O script analisa seu workflow e baixa **apenas os modelos necessários**
3. Após gerar, a GPU é destruída (sem custo fixo)

## � Setup Inicial

### 1. Instale as Dependências
```bash
pip install vastai requests gdown
vastai set api-key SUA_CHAVE_VAST_AI
```

### 2. Configure seus Modelos no Google Drive

1. Suba seus modelos para o Google Drive
2. Compartilhe cada arquivo como **"Qualquer pessoa com o link"**
3. Copie o link de cada modelo

### 3. Configure o `config.json`

Crie um arquivo `config.json` baseado no exemplo:

```json
{
    "api_key": "sua_chave_vast_ai",
    "gpu_query": "RTX_4090",
    "max_price": 0.8,
    "gdrive_models": {
        "checkpoints": {
            "sd_xl_base_1.0.safetensors": "https://drive.google.com/file/d/ABC123/view"
        },
        "loras": {
            "meu_lora.safetensors": "https://drive.google.com/file/d/XYZ789/view"
        },
        "vae": {},
        "controlnet": {},
        "upscale_models": {},
        "embeddings": {},
        "clip": {}
    }
}
```

## 🎨 Uso

### Executar um Workflow
```bash
# O script analisa o workflow e baixa apenas os modelos necessários
python vastai_runner.py --workflow meu_fluxo.json
```

### Parar Cobrança
```bash
python vastai_runner.py --stop
```

## ⚙️ Opções

| Opção | Padrão | Descrição |
|:------|:-------|:----------|
| `--gpu` | RTX_3090 | GPU para buscar |
| `--price` | 0.5 | Preço máximo $/hora |
| `--keep-alive` | false | Manter instância após workflow |

## 📁 Estrutura de Pastas no GDrive

Organize seus modelos assim (opcional, mas ajuda):

```
📁 Meus Modelos ComfyUI/
├── 📁 checkpoints/
│   ├── sd_xl_base_1.0.safetensors
│   └── flux1-dev.safetensors
├── 📁 loras/
│   └── meu_estilo.safetensors
└── 📁 controlnet/
    └── control_v11p_canny.pth
```

## 💰 Custos

| Item | Custo |
|:-----|:------|
| Google Drive | Grátis (15GB) ou R$10/mês (100GB) |
| Vast.ai GPU | ~$0.30-1.00/hora (só quando usar) |
| **Custo Fixo Mensal** | **$0** |

## ⚠️ Importante

1. **Modelos grandes = download lento**: Um checkpoint de 6GB pode demorar alguns minutos para baixar
2. **Sempre pare a instância**: Use `--stop` ou o script destrói automaticamente após o workflow
3. **Links precisam ser públicos**: Configure "Qualquer pessoa com o link" no GDrive
