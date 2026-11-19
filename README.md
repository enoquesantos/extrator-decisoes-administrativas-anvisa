# Extrator de Decisões Administrativas da ANVISA

Ferramenta automatizada em Python desenvolvida para coletar, converter e extrair metadados estruturados do acervo público de decisões administrativas da Agência Nacional de Vigilância Sanitária (ANVISA), disponibilizado na Biblioteca Digital (DSpace).
<br><br>
O projeto foi concebido para viabilizar a construção de uma base de dados empírica (contendo cerca de 9.000 decisões) destinada à filtragem, análise quantitativa e seleção de amostra para pesquisa de Doutorado.

---

## O que o projeto faz

1. **Navegação e Coleta Automatizada (Web Scraping):** Acessa a coleção pública da ANVISA a partir da página inicial (`handle/anvisa/12265`), percorre toda a paginação da tabela `BrowseListTag`, entra na página individual de cada decisão e localiza o link direto do documento no painel *"Arquivos associados a este item:"*.
2. **Organização Rastreável:** Cria um diretório exclusivo para cada decisão identificada pelo seu código único (ex.: `anvisa_22566/`), armazenando nele o arquivo PDF original (`anvisa_22566.pdf`), a transcrição em texto puro (`anvisa_22566.txt`) e a planilha individual correspondente (`anvisa_22566.csv`).
3. **Conversão para Texto:** Extrai o conteúdo textual de todas as páginas de cada PDF baixado e salva em formato `.txt` (UTF-8) para permitir buscas e mineração de dados.
4. **Mineração de Metadados Jurídicos:** Analisa o texto de cada decisão utilizando expressões regulares (Regex) calibradas para o padrão da Lei nº 6.437/1977 e extrai:
   * **Valor da multa aplicada** (em Reais);
   * **Classificação da infração** (*Leve*, *Grave* ou *Gravíssima*);
   * **Incisos do Art. 10 imputados** (em algarismos romanos).
5. **Exportação em CSV:** Gera um arquivo `.csv` individual para cada decisão (mantendo o mesmo nome-base do PDF para rastreabilidade) e alimenta simultaneamente um arquivo mestre (`dataset_consolidado.csv`) contendo: `Arquivo_Rastreio`, `Título da Decisão`, `Data de Publicação`, `Autor`, `URL do PDF`, `Valor da multa aplicada`, `Classificação da Infração` e `Incisos do art. 10 imputados`.
6. **Resiliência e Controle de Falhas:**
   * Aplica uma pausa obrigatória de **3 segundos** entre cada item para evitar sobrecarga ou bloqueio no servidor da ANVISA.
   * Possui retomada inteligente (idempotência): se a execução for interrompida, ao reiniciar o script ele ignora os itens já concluídos e continua de onde parou.
   * Registra em tempo real no arquivo `logs/falhas.log` qualquer falha de rede, link ausente, arquivo vazio, PDF corrompido ou documento digitalizado sem camada de texto.

---

## Bibliotecas Utilizadas

As dependências estão listadas no arquivo `requirements.txt`:

* **`requests` e `urllib3`:** Gerenciam as requisições HTTP com suporte a sessões persistentes, *streaming* de arquivos binários e políticas automáticas de retentativa (*retry* com *backoff* exponencial) para contornar instabilidades temporárias de rede.
* **`beautifulsoup4` e `lxml`:** Realizam o *parsing* rápido e estruturado do HTML das páginas do repositório DSpace da ANVISA, navegando com precisão pelos seletores CSS e atributos da tabela de listagem e dos painéis de arquivos.
* **`pypdf`:** Biblioteca em Python puro responsável por abrir os arquivos PDF baixados, validar sua estrutura interna e extrair o texto de cada página para conversão em `.txt`.

---

## Estrutura do Projeto

```text
anvisa_scraper/
├── requirements.txt
├── config.py
├── scraper.py
├── extractor.py
├── main.py
├── README.md
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
* **`extractor.py`**: Módulo dedicado ao processamento documental. Converte o PDF para texto plano (`converter_pdf_para_txt`) e aplica regras de extração via expressões regulares para capturar o valor da multa (`extrair_valor_multa`), a gravidade da infração (`extrair_classificacao_infracao`) e os incisos do Art. 10 da Lei nº 6.437/77 (`extrair_incisos_art10`).
* **`main.py`**: Orquestrador principal do pipeline. Coordena o loop de paginação, verifica se o item já foi processado anteriormente, aciona sequencialmente o download, a conversão para `.txt`, a extração dos dados e a gravação tanto do `.csv` individual quanto do `dataset_consolidado.csv`, respeitando o intervalo de 3 segundos por decisão.

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

### 4. Execução
Inicie o pipeline de coleta e extração:

```bash
python main.py
```

Durante a execução:
* O progresso de cada decisão será exibido diretamente no terminal.
* Os arquivos extraídos serão salvos continuamente em `dados_extraidos/`.
* Caso ocorra qualquer erro de download ou leitura de PDF corrompido, os detalhes ficarão registrados em `logs/falhas.log`.
* Para interromper a execução com segurança a qualquer momento, pressione `Ctrl + C`. Ao executar `python main.py` novamente, o sistema pulará os itens já concluídos e retomará a coleta.


## Destaques Técnicos da Implementação
- Retomada Inteligente (Idempotência): Com uma pausa de 3 segundos por item, baixar 9.000 decisões levará cerca de 7,5 horas de tempo de espera puro, fora o tempo de download. Se a internet cair no item 4.500, basta rodar python main.py novamente; o script verificará quais pastas já possuem o par .pdf + .csv íntegros e continuará de onde parou.
- Validação de Assinatura Binária (%PDF): Às vezes o servidor do DSpace da ANVISA retorna uma página HTML de manutenção com código HTTP 200. A função baixar_pdf lê os primeiros 5 bytes do arquivo baixado para confirmar que é um PDF real antes de prosseguir, registrando no logs/falhas.log caso contrário.
- PDFs Digitalizados sem OCR: Algumas decisões mais antigas na Biblioteca Digital podem ser imagens escaneadas sem camada de texto. O script detecta quando texto_completo vem vazio e grava um alerta específico no falhas.log para que você possa tratá-los separadamente se necessário.


## Executar a criação de um banco de dados SQLite
- Executar a importação (pode ser rodado a qualquer momento, mesmo durante a coleta parcial):
- python importar_sqlite.py

### O script importar_sqlite atualizado com suporte nativo ao FTS5 (Full-Text Search 5) do SQLite.
A configuração utiliza tokenize='unicode61 remove_diacritics 2', o que significa que suas buscas ignorarão acentos e maiúsculas/minúsculas automaticamente (por exemplo, buscar por rotulagem ou sanitaria encontrará tanto Rotulagem quanto sanitária), além de utilizar external content (content='decisoes') para não duplicar o espaço ocupado pelo texto das 9.000 decisões em disco.


## Correções
- Cada inciso do artigo 10 em uma coluna (para permitir contar o número automaticamente)
- Dúvidas: De qual campo está pegando o data? O correto é extrair do campo assinatura, no fim da página.

### Acrescentar:
- Origem AIS (o código está no próprio número do AIS, em posição fixa após o hífen): ex: GGFIS-DF, CMPAF, PVPAF, COPAS
- Risco: baixo, médio, alto, muito alto 
- Primariedade (buscar primeiro por "reincidente", porque a palavra "primária" pode aparecer em contexto negativo): primário ou reincidente
- Porte (extrair o porte da seção de dosimetria, não de menções anteriores): PF ou Porte (ex: Microempresa, Médio Porte Grupo IV, Grande Porte Grupo I)


## Melhorias futuras
- Adicionar OCR automático com Tesseract para PDFs escaneados
- Importar todos os CSVs individuais em um banco PostgreSQL/SQLite
- Refinar as expressões regulares para capturar CNPJ e Processo
