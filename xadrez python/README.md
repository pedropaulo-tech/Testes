# Xadrez Python

Um jogo de xadrez completo para desktop, desenvolvido em Python com
`pygame` e `python-chess`. A interface permite partidas locais, desfazer e
refazer lances, girar o tabuleiro e jogar contra uma IA opcional usando
Ollama.

## Funcionalidades

- Regras completas de xadrez, incluindo roque, captura en passant e promoção
- Destaques para a peça selecionada, os lances legais e o último lance
- Indicação visual de xeque e status da partida
- Histórico de lances em notação SAN
- Cálculo simples da vantagem material
- Desfazer e refazer lances
- Rotação do tabuleiro
- Reinício da partida
- Adversário IA com escolha do lado e da dificuldade
- Suporte a modelos Ollama locais
- Jogada automática local quando o Ollama não está disponível

## Requisitos

- Python 3.10 ou superior
- Pygame
- python-chess

O projeto inclui um [requirements.txt](requirements.txt) com as dependências.

## Instalação

Na pasta do projeto, crie e ative um ambiente virtual:

```bash
python -m venv .venv
source .venv/bin/activate
```

No Windows, use:

```bat
python -m venv .venv
.venv\Scripts\activate
```

Instale as dependências:

```bash
python -m pip install -r requirements.txt
```

## Executando

Com o ambiente virtual ativo, execute:

```bash
python xadrez.py
```

A aplicação abre uma janela de 920 por 640 pixels. Quando nenhuma imagem de
peça estiver disponível em `assets/pieces`, os símbolos Unicode serão usados
como alternativa.

## Como jogar

1. Clique em uma peça da cor correspondente ao turno.
2. Clique em uma casa destacada para mover a peça.
3. Ao promover um peão, escolha a dama, torre, bispo ou cavalo na tela.
4. Use os botões no painel direito para desfazer, refazer, virar o tabuleiro,
   reiniciar ou configurar a IA.

### Atalhos do teclado

| Tecla | Ação |
|---|---|
| `U` ou `←` | Desfazer |
| `R` ou `→` | Refazer |
| `F` | Virar o tabuleiro |
| `N` | Reiniciar a partida |
| `Esc` | Cancelar seleção ou promoção |
| `P` | Solicitar empate por 50 lances ou repetição |

## Adversário IA

Clique em **IA: configurar** para escolher:

- Jogador com as brancas ou com as pretas
- Dificuldade fácil, equilibrada ou difícil
- Um modelo Ollama instalado, quando disponível

A IA consulta o servidor Ollama em `http://127.0.0.1:11434`. Se nenhum modelo
ou servidor estiver disponível, o jogo utiliza uma jogada local segura:

- leva capturas e xeques em consideração;
- prefere xeque-mate;
- seleciona aleatoriamente entre os melhores lances locais disponíveis.

## Estrutura

```text
xadrez python/
├── assets/
│   └── pieces/          # Imagens das peças
├── .vscode/
│   └── settings.json    # Configuração opcional do VS Code
├── requirements.txt     # Dependências do projeto
├── xadrez.py            # Código principal
└── README.md
```

## Créditos

Feito por [@joaorizzo0112](https://github.com/joaorizzo0112).
