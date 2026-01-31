# ComfyUI + Vast.ai 🚀

Arquitetura híbrida para ComfyUI com otimização de custos:
- **Coolify (VPS)**: Interface web CPU-only para design de workflows
- **Vast.ai**: GPUs sob demanda para processamento

## 🏗️ Arquitetura

```
┌─────────────────────────────────────────────────────────────┐
│                    Seu Fluxo de Trabalho                    │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│   ┌─────────────┐         ┌─────────────────────────────┐   │
│   │   COOLIFY   │         │         VAST.AI             │   │
│   │  (CPU-only) │         │      (GPU sob demanda)      │   │
│   │             │         │                             │   │
│   │  ComfyUI UI │ ──────► │  RTX 3090/4090 processing   │   │
│   │  Criar/Editar         │  Paga apenas quando usa     │   │
│   │  workflows  │ ◄────── │  ~$0.20-0.80/hora           │   │
│   │             │         │                             │   │
│   │   GRÁTIS    │         │                             │   │
│   └─────────────┘         └─────────────────────────────┘   │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

## 🚀 Deploy no Coolify

### 1. Adicionar Recurso
1. Acesse seu Coolify
2. **+ Add Resource** → **Docker Compose**
3. Conecte: `galhosostore-coder/ComfyUI-VastAI`
4. Deploy!

### 2. Configurar Environment Variables

No Coolify, vá em **Environment Variables** e configure:

| Variável | Descrição | Default |
|----------|-----------|---------|
| `COMFYUI_PORT` | Porta do ComfyUI | `8188` |
| `VASTAI_API_KEY` | Sua API Key do Vast.ai | - |
| `VASTAI_MAX_PRICE` | Preço máximo/hora (USD) | `0.50` |
| `VASTAI_PREFERRED_GPUS` | GPUs preferidas | `RTX 3090,RTX 4090` |
| `MEMORY_LIMIT` | Limite de RAM | `2G` |

> 💡 **Dica**: Copie as variáveis do arquivo `.env.example` para o Coolify

### 3. Acessar
```
https://seu-dominio:8188
```

---

## 🎮 Usando Vast.ai para Processamento

### Configuração

1. Crie conta em [vast.ai](https://vast.ai)
2. Copie sua API Key
3. Cole no Coolify: `VASTAI_API_KEY=sua_key`

### Comandos (via terminal do container)

```bash
# Buscar GPUs disponíveis
python /app/scripts/vastai_manager.py search

# Iniciar GPU
python /app/scripts/vastai_manager.py start

# Verificar status
python /app/scripts/vastai_manager.py status

# ⚠️ IMPORTANTE: Parar quando terminar!
python /app/scripts/vastai_manager.py stop
```

---

## 💰 Estimativa de Custos

| GPU | Preço/Hora | Uso (1h/dia) |
|-----|------------|--------------|
| RTX 3090 | $0.20-0.40 | ~$6-12/mês |
| RTX 4090 | $0.40-0.80 | ~$12-24/mês |

---

## 📁 Estrutura

```
ComfyUI-VastAI/
├── docker-compose.yml    # Config Docker (editável via Coolify)
├── .env.example          # Template de variáveis
├── data/
│   ├── input/           # Imagens de entrada
│   ├── output/          # Resultados
│   └── workflows/       # Seus workflows
└── scripts/
    └── vastai_manager.py
```

## 📄 Licença

MIT
