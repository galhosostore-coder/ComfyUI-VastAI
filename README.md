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

## 📋 Pré-requisitos

- VPS com Coolify instalado
- Conta no [Vast.ai](https://vast.ai) (para processamento GPU)
- Repositório Git (GitHub, GitLab, etc.)

## 🚀 Deploy no Coolify

### 1. Preparar Repositório

```bash
# Clone este repositório
git clone https://github.com/SEU_USUARIO/ConfyUI-VastIA.git
cd ConfyUI-VastIA

# Configure suas credenciais
cp .env.example .env
# Edite .env com sua API key do Vast.ai
```

### 2. Deploy no Coolify

1. Acesse seu painel Coolify
2. **+ Add Resource** → **Docker Compose**
3. Conecte seu repositório GitHub
4. Selecione este repositório
5. Coolify detectará automaticamente o `docker-compose.yml`
6. Clique em **Deploy**

### 3. Acessar ComfyUI

Após o deploy, acesse:
```
https://seu-dominio.com:8188
```

Ou configure um proxy reverso no Coolify para ter acesso via HTTPS.

## 🎮 Usando Vast.ai para Processamento

### Configuração Inicial

```bash
# Instale dependências
cd scripts
pip install -r requirements.txt

# Configure API key
# Obtenha em: https://vast.ai/console/account
echo "VASTAI_API_KEY=sua_api_key" > ../.env
```

### Comandos Disponíveis

```bash
# Buscar GPUs disponíveis (até $0.50/hora)
python vastai_manager.py search --price 0.50

# Iniciar uma GPU
python vastai_manager.py start --price 0.40

# Verificar status
python vastai_manager.py status

# Processar um workflow
python vastai_manager.py process ../data/workflows/meu_workflow.json

# ⚠️ IMPORTANTE: Parar quando terminar (para de cobrar!)
python vastai_manager.py stop
```

## 💰 Estimativa de Custos

| GPU | Preço/Hora | Uso Típico (1h/dia) |
|-----|------------|---------------------|
| RTX 3090 | $0.20-0.40 | ~$6-12/mês |
| RTX 4090 | $0.40-0.80 | ~$12-24/mês |
| A100 40GB | $1.00-2.00 | ~$30-60/mês |

> 💡 **Dica**: Use o comando `stop` assim que terminar para maximizar economia!

## 📁 Estrutura do Projeto

```
ConfyUI-VastIA/
├── docker-compose.yml    # Config Docker para Coolify
├── .env.example          # Template de variáveis
├── .gitignore
├── README.md
├── data/
│   ├── input/           # Imagens de entrada
│   ├── output/          # Imagens geradas
│   ├── workflows/       # Seus workflows JSON
│   └── custom_nodes/    # Nodes customizados
└── scripts/
    ├── vastai_manager.py    # Gerenciador de GPUs
    └── requirements.txt
```

## 🔧 Fluxo de Trabalho Recomendado

1. **Design** (Coolify - GRÁTIS)
   - Acesse ComfyUI na VPS
   - Crie/edite seus workflows
   - Salve como JSON em `data/workflows/`

2. **Processamento** (Vast.ai - PAGO)
   ```bash
   python vastai_manager.py start        # Inicia GPU
   python vastai_manager.py status       # Confirma que está rodando
   # Use o IP/porta exibido para acessar ComfyUI com GPU
   # ... faça suas gerações ...
   python vastai_manager.py stop         # PARA DE COBRAR!
   ```

3. **Resultados**
   - Baixe resultados da instância Vast.ai
   - Ou configure S3 para transferência automática

## ❓ FAQ

**P: Posso gerar imagens diretamente na VPS?**
R: Tecnicamente sim, mas será MUITO lento (minutos por imagem). A VPS é apenas para design de workflows.

**P: Quanto tempo leva para iniciar uma GPU?**
R: Geralmente 2-5 minutos para a instância ficar pronta.

**P: E se eu esquecer de parar a GPU?**
R: Configure um alerta no Vast.ai ou use o comando `status` regularmente. Você pode definir gastos máximos na conta.

## 📄 Licença

MIT
