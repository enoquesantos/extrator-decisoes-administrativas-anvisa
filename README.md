# Extrator de Decisões Administrativas da ANVISA

Ferramenta automatizada em Python desenvolvida para coletar, converter, auditar e estruturar em banco de dados o acervo público de decisões administrativas da Agência Nacional de Vigilância Sanitária (ANVISA), disponibilizado na Biblioteca Digital (DSpace).

O projeto foi concebido para viabilizar a construção de uma base de dados empírica (contendo cerca de 9.000 decisões) destinada à filtragem, análise quantitativa e seleção de amostra para pesquisa de Doutorado.

---

## O que o projeto faz

1. **Navegação e Coleta Automatizada (Web Scraping):** Acessa a coleção pública da ANVISA a partir da página inicial (`handle/anvisa/12265`), percorre toda a paginação da tabela `BrowseListTag`, entra na página individual de cada decisão e localiza o link direto do documento no painel *"Arquivos associados a este item:"*.
2. **Organização Rastreável:** Cria um diretório exclusivo para cada decisão identificada pelo seu código único (ex.: `anvisa_22566/`), armazenando nele o arquivo PDF original (`anvisa_22566.pdf`), a transcrição em texto puro (`anvisa_22566.txt`) e a planilha individual correspondente (`anvisa_22566.csv`).
3. **Conversão para Texto:** Extrai o conteúdo textual de todas as páginas de cada PDF baixado e salva em formato `.txt` (UTF-8) para permitir buscas e mineração de dados.
4. **Mineração de Metadados Jurídicos:** Analisa o texto de cada decisão utilizando expressões regulares (Regex) calibradas para o padrão da Lei nº 6.437/1977 e extrai:
   * **Data da Assinatura:** Extraída do final do documento (carimbo de assinatura eletrônica do SEI ou fecho datado), complementando a data de publicação do DSpace;
   * **Origem AIS:** Código da unidade autuadora extraído em posição fixa após o hífen no número do Auto de Infração Sanitária (ex.: `GGFIS-DF`, `CMPAF`, `PVPAF`, `COPAS`);
   * **Risco Sanitário:** `Baixo`, `Médio`, `Alto` ou `Muito Alto`;
   * **Primariedade:** `Primário` ou `Reincidente` (verificando primeiro contextos de reincidência e negações explícitas para evitar falsos positivos com a palavra *"primária"* em sentido negativo);
   * **Porte Econômico:** Extraído especificamente da seção de dosimetria da pena (ex.: `PF`, `Microempresa`, `Empresa de Pequeno Porte`, `Médio Porte Grupo III/IV`, `Grande Porte Grupo I/II`);
   * **Valor da multa aplicada:** Valores pecuniários em Reais (com conversão numérica no banco de dados);
   * **Classificação da infração:** `Leve`, `Grave` ou `Gravíssima`;
   * **Incisos do Art. 10 imputados:** Lista resumida, contagem total (`Total_Incisos_Art10`) e **42 colunas binárias individuais** (`Art10_I` a `Art10_XLII`, preenchidas com `1` ou `0` para contagem automática).
5. **Exportação em CSV, SQLite (com FTS5) e Excel (`.xlsx`):** Gera arquivos `.csv` individuais e um `dataset_consolidado.csv`, importa os dados para um banco relacional `anvisa_decisoes.db` com índice de busca textual avançada (FTS5), audita a taxa de sucesso da extração e exporta relatórios analíticos prontos em abas de Excel (`relatorio_consultas_tese.xlsx`).
6. **Resiliência e Controle de Falhas:**
   * Aplica uma pausa obrigatória de **3 segundos** entre cada item para evitar sobrecarga ou bloqueio no servidor da ANVISA.
   * Possui retomada inteligente (idempotência): se a execução for interrompida, ao reiniciar o script ele ignora os itens já concluídos e continua de onde parou.
   * Registra em tempo real no arquivo `logs/falhas.log` qualquer falha de rede, link ausente, arquivo vazio, PDF corrompido ou documento digitalizado sem camada de texto.

---

## Bibliotecas Utilizadas

As dependências externas estão listadas no arquivo `requirements.txt`:

* **`requests` e `urllib3`:** Gerenciam as requisições HTTP com suporte a sessões persistentes, *streaming* de arquivos binários e políticas automáticas de retentativa (*retry* com *backoff* exponencial) para contornar instabilidades temporárias de rede.
* **`beautifulsoup4` e `lxml`:** Realizam o *parsing* rápido e estruturado do HTML das páginas do repositório DSpace da ANVISA, navegando com precisão pelos seletores CSS e atributos da tabela de listagem e dos painéis de arquivos.
* **`pypdf`:** Biblioteca em Python puro responsável por abrir os arquivos PDF baixados, validar sua estrutura interna e extrair o texto de cada página para conversão em `.txt`.
* **`openpyxl`:** Biblioteca em Python puro utilizada para gerar o relatório final em Excel (`.xlsx`) com múltiplas abas, formatação monetária, filtros automáticos e ajuste de colunas.

Além dessas, o projeto utiliza módulos nativos da biblioteca padrão do Python (`sqlite3`, `argparse`, `csv`, `re`, `logging`, `pathlib`).

---

## Estrutura do Projeto

```text
anvisa_scraper/
├── auditoria_extracao.py
├── config.py
├── consultas_tese.sql
├── exportar_excel.py
├── extractor.py
├── importar_sqlite.py
├── LICENSE
├── main.py
├── README.md
├── requirements.txt
├── scraper.py
├── anvisa_decisoes.db            # Gerado após rodar importar_sqlite.py
├── relatorio_consultas_tese.xlsx # Gerado após rodar exportar_excel.py
├── logs/
│   └── falhas.log
└── dados_extraidos/
    ├── anvisa_22566/
    │   ├── anvisa_22566.pdf
    │   ├── anvisa_22566.txt
    │   └── anvisa_22566.csv
    └── dataset_consolidado.csv
```

### Descrição dos Arquivos

* **`requirements.txt`**: Lista os pacotes externos necessários e suas versões mínimas para reprodução do ambiente.
* **`config.py`**: Centraliza as configurações globais do projeto, incluindo a URL inicial da ANVISA, o tempo de espera entre requisições (`SLEEP_TIME = 3`), os cabeçalhos HTTP (`User-Agent`), a criação automática das pastas de saída e a configuração do `logging` que grava os erros imediatamente em `logs/falhas.log`.
* **`scraper.py`**: Módulo responsável pela interação com o portal da ANVISA. Contém as funções para criar a sessão HTTP resiliente, varrer as tabelas de listagem e paginação (`extrair_itens_listagem`), acessar a página secundária de cada decisão para capturar a URL do arquivo e metadados Dublin Core (`obter_url_pdf_e_metadados`), além de realizar o download validando a assinatura binária `%PDF` (`baixar_pdf`).
* **`extractor.py`**: Módulo dedicado ao processamento documental. Converte o PDF para texto plano (`converter_pdf_para_txt`) e aplica regras de extração via expressões regulares para capturar `Data da Assinatura`, `Origem AIS`, `Risco`, `Primariedade`, `Porte` (na seção de dosimetria), `Valor da multa aplicada`, `Classificação da Infração` e os **42 incisos do Art. 10** da Lei nº 6.437/1977 em formato binário (`0` ou `1`).
* **`main.py`**: Orquestrador principal do pipeline de coleta. Coordena o loop de paginação, suporta execução em modo de teste via argumento `--limite`, verifica se o item já foi processado anteriormente, aciona sequencialmente o download, a conversão para `.txt`, a extração dos dados e a gravação tanto do `.csv` individual quanto do `dataset_consolidado.csv`, respeitando o intervalo de 3 segundos por decisão.
* **`importar_sqlite.py`**: Lê todos os CSVs individuais e arquivos `.txt` gerados em `dados_extraidos/` e os carrega no banco relacional `anvisa_decisoes.db`. Normaliza os incisos do Art. 10 na tabela `decisao_incisos`, converte valores monetários para tipo numérico (`REAL`), extrai o ano de referência prioritariamente da `Data da Assinatura` e cria a tabela virtual `decisoes_fts` (FTS5) com *triggers* automáticas de sincronização.
* **`consultas_tese.sql`**: Biblioteca de 13 consultas SQL prontas e comentadas para análise empírica da amostra, cobrindo filtros por gravidade/valor, ranking de incisos do Art. 10, buscas booleanas e de proximidade (`NEAR`) via FTS5, séries históricas anuais e estatísticas agregadas por `Classificação`, `Origem AIS`, `Risco`, `Primariedade` e `Porte`.
* **`exportar_excel.py`**: Conecta-se ao `anvisa_decisoes.db`, monta a aba `0. BASE COMPLETA` (matriz com todos os registros e as 42 colunas binárias `Art10_I` a `Art10_XLII`) e executa dinamicamente todas as consultas de `consultas_tese.sql`, exportando cada resultado para uma aba formatada em `relatorio_consultas_tese.xlsx`.
* **`auditoria_extracao.py`**: Script de diagnóstico de qualidade que consulta o `anvisa_decisoes.db` e exibe no terminal a proporção de PDFs com texto extraível versus prováveis imagens escaneadas, a taxa de sucesso (*Encontrado* vs. *Não encontrado*) para cada campo e uma amostra de IDs para calibração das expressões regulares.

---

## Colunas Geradas no CSV e na Base Analítica

Cada arquivo `.csv` individual (e o `dataset_consolidado.csv`) contém as seguintes colunas separadas por ponto e vírgula (`;`) em codificação `UTF-8-SIG`:

| Coluna | Descrição |
| :--- | :--- |
| `Arquivo_Rastreio` | Nome do arquivo PDF correspondente (ex.: `anvisa_22566.pdf`). |
| `Título da Decisão` | Título registrado na Biblioteca Digital da ANVISA. |
| `Data da Assinatura` | Data extraída do campo de assinatura no final do PDF (`DD/MM/AAAA`). |
| `Data de Publicação (DSpace)` | Data de disponibilização registrada no repositório DSpace. |
| `Autor` | Autor ou órgão julgador listado no repositório. |
| `URL do PDF` | Link direto para o arquivo PDF original no portal da ANVISA. |
| `Origem AIS` | Sigla da área autuadora após o hífen no número do AIS (ex.: `GGFIS-DF`, `CMPAF`, `PVPAF`, `COPAS`). |
| `Risco` | Nível de risco sanitário (`Baixo`, `Médio`, `Alto`, `Muito Alto`). |
| `Primariedade` | Condição do infrator (`Primário` ou `Reincidente`). |
| `Porte` | Porte econômico extraído da seção de dosimetria (ex.: `PF`, `Microempresa`, `Médio Porte Grupo IV`, `Grande Porte Grupo I`). |
| `Valor da multa aplicada` | Valor(es) pecuniário(s) em Reais extraídos da decisão. |
| `Classificação da Infração` | Gravidade da infração (`Leve`, `Grave`, `Gravíssima`). |
| `Incisos do art. 10 imputados` | Lista consolidada dos incisos imputados em algarismos romanos (ex.: `IV, XXIX`). |
| `Total_Incisos_Art10` | Quantidade numérica total de incisos do Art. 10 identificados na decisão. |
| `Art10_I` até `Art10_XLII` | 42 colunas binárias (`1` = imputado, `0` = não imputado) para contagem e soma automática. |

---

## Como Executar o Projeto

### 1. Pré-requisitos
Certifique-se de ter o **Python 3.10 ou superior** instalado em seu sistema.

### 2. Configuração do Ambiente Virtual
Acesse a pasta raiz do projeto pelo terminal, crie e ative um ambiente virtual isolado:

**No macOS / Linux:**
```bash
python3 -m venv .venv
source .venv/bin/activate
```

**No Windows (PowerShell):**
```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
```

### 3. Instalação das Dependências
Com o ambiente virtual ativado, atualize o `pip` e instale as bibliotecas:

```bash
pip install --upgrade pip
pip install -r requirements.txt
```

### 4. Execução do Pipeline de Coleta (`main.py`)

**Modo de teste rápido (recomendado antes da coleta completa):**
Baixa e processa apenas os 5 primeiros novos documentos para validação:
```bash
python main.py --limite 5
```

**Coleta completa:**
Percorre toda a paginação do acervo (os itens já processados no teste são reaproveitados automaticamente):
```bash
python main.py
```

Durante a execução:
* O progresso de cada decisão é exibido diretamente no terminal com um resumo dos campos extraídos.
* Os arquivos são salvos continuamente em `dados_extraidos/`.
* Erros de download, arquivos corrompidos ou PDFs sem camada de texto são registrados em `logs/falhas.log`.
* Para pausar com segurança a qualquer momento, pressione `Ctrl + C`. Ao executar `python main.py` novamente, a coleta retomará de onde parou.

### 5. Criação e Atualização do Banco de Dados SQLite (`importar_sqlite.py`)
Pode ser executado a qualquer momento (inclusive durante coletas parciais):
```bash
python importar_sqlite.py
```
*(Nota: caso atualize a estrutura de colunas sobre um banco antigo de testes, remova o arquivo `anvisa_decisoes.db` antes de rodar a importação).*

### 6. Auditoria da Qualidade da Extração (`auditoria_extracao.py`)
Exibe o percentual de preenchimento de cada campo e lista exemplos de documentos para eventual ajuste fino das expressões regulares:
```bash
python auditoria_extracao.py
```

### 7. Exportação de Relatórios para Excel (`exportar_excel.py`)
Gera a planilha `relatorio_consultas_tese.xlsx` contendo a base completa com as 42 colunas de incisos e uma aba formatada para cada consulta definida em `consultas_tese.sql`:
```bash
python exportar_excel.py
```

---

## Destaques Técnicos da Implementação

* **Retomada Inteligente (Idempotência):** Com uma pausa de 3 segundos por item, baixar 9.000 decisões exige cerca de 7,5 horas de tempo de espera puro, fora o tempo de download. Em caso de queda de conexão, basta rodar `python main.py` novamente; o script verifica quais pastas já possuem o par `.pdf` + `.csv` íntegros e continua de onde parou.
* **Validação de Assinatura Binária (`%PDF`):** Para evitar salvar páginas HTML de manutenção retornadas com código HTTP 200, a função `baixar_pdf` inspeciona os primeiros 5 bytes de cada arquivo baixado para confirmar que se trata de um PDF válido, registrando falhas em `logs/falhas.log`.
* **Detecção de PDFs Digitalizados sem OCR:** Decisões antigas escaneadas como imagem sem camada de texto são detectadas automaticamente quando a extração retorna vazia, gerando um alerta específico em `logs/falhas.log` e sendo contabilizadas separadamente no `auditoria_extracao.py`.
* **Busca Textual Avançada (SQLite FTS5):** A tabela virtual `decisoes_fts` utiliza `tokenize='unicode61 remove_diacritics 2'` (ignorando acentos e maiúsculas/minúsculas em buscas booleanas e de proximidade `NEAR`) com `content='decisoes'` (*external content*), evitando duplicar o espaço em disco ocupado pelo texto completo das decisões.

---

## Melhorias Futuras

* Adicionar fallback de OCR automático (com Tesseract ou EasyOCR) para processar PDFs escaneados sem camada de texto.
* Criar script de reprocessamento offline (`reprocessar_local.py`) para regerar os CSVs a partir dos `.txt` já baixados sempre que alguma expressão regular for refinada.
* Refinar as expressões regulares para capturar também o CNPJ do autuado, o número do Processo Administrativo Sanitário (PAS) e o desfecho recursal.
* Adicionar suporte opcional de exportação para banco de dados PostgreSQL.