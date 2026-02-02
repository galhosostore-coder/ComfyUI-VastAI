# ComfyUI Híbrido: Coolify + Vast.ai

Este projeto permite que você execute uma instância leve do ComfyUI no seu servidor Coolify (Contabo) para **criar e visualizar** fluxos de trabalho, e use o poder da **Vast.ai** para o processamento pesado de imagens/vídeos sob demanda.

## Estrutura do Projeto

- **Dockerfile**: Configuração para instalar o ComfyUI no Coolify (modo CPU, baixo consumo).
- **vastai_runner.py**: Script Python para alugar automaticamente uma GPU na Vast.ai, executar o trabalho e encerrar a máquina (economizando dinheiro).
- **requirements.txt**: Dependências necessárias.

## Passo 1: Instalação no Coolify

1.  Crie um novo recurso no Coolify e selecione sua fonte (GitHub, GitLab, etc.) onde você hospedou estes arquivos.
2.  O Coolify detectará o `Dockerfile` automaticamente.
3.  **Configurações de Build**:
    -   Certifique-se de que a porta exposta seja `8188`.
4.  **Implante (Deploy)**.
5.  Após o deploy, você poderá acessar o ComfyUI pelo domínio configurado no Coolify.
    -   *Nota*: Esta instância roda em CPU. Ela serve para criar os nós (nodes) e salvar o workflow, mas será lenta se tentar gerar imagens complexas nela mesma.

## Passo 2: Configuração da Vast.ai

1.  Crie uma conta na [Vast.ai](https://vast.ai/).
2.  Adicione créditos à sua conta.
3.  Vá em **Account** (Conta) -> **API Key** e copie sua chave.
4.  Instale a ferramenta de linha de comando `vastai` no seu computador (onde você rodará o script de automação):
    ```bash
    pip install vastai requests websocket-client
    ```
5.  Defina sua chave de API:
    ```bash
    vastai set api-key SUA_CHAVE_AQUI
    ```

## Configuração via Variáveis de Ambiente (Coolify)

Se você estiver rodando este script dentro do container do Coolify (ou apenas quiser configurar via sistema), você pode usar as seguintes **Variáveis de Ambiente** na aba "Environment Variables" do seu projeto no Coolify. Isso torna mais seguro e fácil de alterar sem mexer no código.

| Variável | Descrição | Exemplo |
| :--- | :--- | :--- |
| `VAST_API_KEY` | **Obrigatório**. Sua chave de API da Vast.ai. | `81237...` |
| `VAST_GPU` | (Opcional) Nome da GPU para buscar. Padrão: `RTX_3090`. | `RTX_4090` |
| `VAST_PRICE` | (Opcional) Preço máximo por hora em dólares. Padrão: `0.5`. | `1.5` |
| `VAST_KEEP_ALIVE` | (Opcional) Se `true`, não destrói a máquina ao final. | `true` |

*Nota*: Se você definir essas variáveis, não precisa passar argumentos para o script, nem criar o `config.json`. O script dará prioridade para o que estiver nas variáveis de ambiente!

## Passo 3: Como Usar (Fluxo de Trabalho)

1.  **Criar o Workflow**:
    -   Acesse seu ComfyUI no Coolify.
    -   Monte seu fluxo de trabalho.
    -   Clique no botão de engrenagem (Configurações) e ative **"Enable Dev mode Options"**.
    -   Agora aparecerá um botão **"Save (API Format)"**. Clique nele para baixar o arquivo `.json` (ex: `workflow_api.json`).

2.  **Executar na Vast.ai**:
    -   No seu computador (Windows), abra o terminal (PowerShell ou CMD) na pasta deste projeto.
    -   Execute o script `vastai_runner.py` apontando para o arquivo que você baixou:

    ```bash
    # Exemplo: Rodar usando uma RTX 3090 (padrão) e gastando no max $0.50/hora
    python vastai_runner.py --workflow caminho/para/workflow_api.json
    
    # Exemplo: Procurar por uma 4090
    python vastai_runner.py --workflow workflow.json --gpu "RTX_4090" --price 0.8
    ```

3.  **O que o script faz**:
    -   Procura a máquina mais barata na Vast.ai que atenda aos critérios.
    -   Aluga a máquina.
    -   Instala/Inicia o ComfyUI nela.
    -   Envia seu workflow.
    -   Aguarda o processamento.
    -   **Baixa as imagens geradas** para a pasta `vast_outputs`.
    -   **Destrói a máquina** imediatamente após o fim (para parar a cobrança).

## Notas Importantes

- **Custom Nodes**: Se seu workflow usa "Custom Nodes", a máquina da Vast.ai precisa tê-los instalados. O script usa uma imagem padrão (`yanwk/comfyui-boot`) que já vem com muitos nodes populares (ComfyUI-Manager, ControlNet, etc). Se faltar algum, o workflow falhará.
    -   *Dica avançada*: Para workflows muito específicos, você pode precisar editar o script para instalar nodes extras na inicialização (`--onstart-cmd`).
