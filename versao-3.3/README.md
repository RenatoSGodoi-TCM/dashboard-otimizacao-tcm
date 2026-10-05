# Sistema de Apoio à Decisão: Otimização de Componentes para Cadeiras de Rodas

Este repositório contém o código-fonte e os dados estruturados de um Sistema de Apoio à Decisão interativo, desenvolvido em Python e Streamlit. O software aplica modelos de Programação Linear Inteira Mista (PLIM) para otimizar a aquisição de componentes customizados para cadeiras de rodas, resolvendo o trade-off entre custo financeiro e qualidade dos fornecedores.

## Metodologia e Arquitetura

O fluxo de processamento do dashboard foi desenhado seguindo as etapas tradicionais de **Knowledge Discovery in Databases (KDD)**:

* **Seleção e Pré-processamento:** Leitura e normalização de strings dos arquivos JSON de demanda (`prescricoes_v2_pacientes.json`) e catálogo (`dataset_7_componentes.json`).
* **Transformação:** Mapeamento dinâmico de similaridade para cruzar as prescrições médicas com os IDs únicos do catálogo de fornecedores.
* **Data Mining (Otimização):** Aplicação do solver `PuLP` (algoritmo CBC) para resolver a formulação MILP, minimizando custos e penalidades orçamentárias enquanto maximiza a pontuação de qualidade.
* **Avaliação e Interpretação:** Renderização dos resultados em um dashboard interativo (Streamlit e Plotly) para análise de sensibilidade e construção da Fronteira de Pareto empírica.

## Estrutura de Arquivos

* `dash-tcm3.3.py`: Script principal contendo a interface web e a lógica do motor de otimização.
* `dataset_7_componentes.json`: Catálogo planificado de peças e fornecedores.
* `dataset-prescricoes-manuais.json`: Base de dados contendo as prescrições de componentes por paciente.
* `requirements.txt`: Lista de dependências e bibliotecas necessárias.

## Instalação e Requisitos

Certifique-se de ter o Python 3.10+ instalado. Para instalar as bibliotecas necessárias, execute o comando abaixo no terminal:

```bash
pip install -r requirements.txt
```
## Como Executar

O projeto foi desenvolvido e testado utilizando o ambiente do PyCharm. Para executar o dashboard, siga os passos abaixo:

1. Abra a aba **Terminal** na parte inferior do seu PyCharm (ou o terminal de sua preferência).
2. Certifique-se de estar no mesmo diretório onde os arquivos do projeto foram extraídos.
3. Digite o seguinte comando e pressione Enter:

```bash
   streamlit run dash-tcm3.3.py
```

4. Para encerrar a execução digite o seguinte comando e pressione Enter:
```bash
   ctrl + c
```
