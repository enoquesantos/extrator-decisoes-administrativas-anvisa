-- ============================================================================
-- CONSULTAS DE ANÁLISE E FILTRAGEM DA AMOSTRA - DECISÕES ANVISA (SQLite + FTS5)
-- Banco alvo: anvisa_decisoes.db
-- sqlite3 anvisa_decisoes.db < consultas_tese.sql
-- ============================================================================


-- ----------------------------------------------------------------------------
-- 1. FILTRO POR GRAVIDADE E FAIXA DE VALOR MONETÁRIO
-- O que faz: Seleciona todas as decisões classificadas como 'Gravíssima' cuja
-- multa principal seja superior a R$ 50.000,00, ordenando da maior multa para
-- a menor. Útil para isolar sanções de alto impacto financeiro na amostra.
-- ----------------------------------------------------------------------------
SELECT
    item_id,
    ano_publicacao,
    titulo,
    multa_principal_num,
    valor_multa_raw,
    incisos_art_10_raw
FROM decisoes
WHERE classificacao_infracao LIKE '%Gravíssima%'
  AND multa_principal_num > 50000
ORDER BY multa_principal_num DESC;


-- ----------------------------------------------------------------------------
-- 2. RANKING DE FREQUÊNCIA DOS INCISOS DO ART. 10 (LEI Nº 6.437/1977)
-- O que faz: Agrupa a tabela normalizada 'decisao_incisos' para contabilizar
-- quantas decisões imputaram cada inciso do Art. 10, exibindo do mais
-- recorrente ao menos recorrente.
-- ----------------------------------------------------------------------------
SELECT
    inciso,
    COUNT(*) AS total_decisoes
FROM decisao_incisos
GROUP BY inciso
ORDER BY total_decisoes DESC;


-- ----------------------------------------------------------------------------
-- 3. CRUZAMENTO ENTRE INCISO ESPECÍFICO E TERMO NO TEXTO (FILTRO RELACIONAL)
-- O que faz: Realiza um JOIN entre a tabela principal e a tabela de incisos
-- para localizar decisões que imputaram especificamente o inciso 'IV' do
-- Art. 10 e que mencionam a palavra 'medicamento' no corpo do texto.
-- ----------------------------------------------------------------------------
SELECT
    d.item_id,
    d.data_publicacao,
    d.valor_multa_raw,
    d.classificacao_infracao,
    d.url_pdf
FROM decisoes d
JOIN decisao_incisos i ON d.item_id = i.item_id
WHERE i.inciso = 'IV'
  AND d.texto_completo LIKE '%medicamento%';


-- ----------------------------------------------------------------------------
-- 4. BUSCA TEXTUAL BOOLEANA (FTS5) COMBINADA COM FILTRO DE MULTA
-- O que faz: Utiliza o índice invertido FTS5 (ignorando acentos e maiúsculas)
-- para encontrar decisões que tratem de 'propaganda' OU 'publicidade'
-- relacionadas a 'medicamento', excluindo documentos que citem 'alimento',
-- e filtra apenas multas acima de R$ 10.000,00. A função snippet() extrai um
-- trecho de 25 palavras ao redor dos termos destacados entre >>> e <<<.
-- ----------------------------------------------------------------------------
SELECT
    d.item_id,
    d.ano_publicacao,
    d.multa_principal_num,
    d.classificacao_infracao,
    snippet(decisoes_fts, 2, '>>>', '<<<', '...', 25) AS trecho_encontrado
FROM decisoes_fts
JOIN decisoes d ON d.rowid = decisoes_fts.rowid
WHERE decisoes_fts MATCH '(propaganda OR publicidade) AND medicamento NOT alimento'
  AND d.multa_principal_num > 10000
ORDER BY rank;


-- ----------------------------------------------------------------------------
-- 5. BUSCA POR PROXIMIDADE SEMÂNTICA (OPERADOR NEAR DO FTS5)
-- O que faz: Localiza decisões onde o termo 'reincidencia' aparece a uma
-- distância máxima de 15 palavras da palavra 'agravante' (em qualquer ordem e
-- com ou sem acentuação), retornando o contexto exato da dosimetria da pena.
-- ----------------------------------------------------------------------------
SELECT
    d.item_id,
    d.titulo,
    d.valor_multa_raw,
    snippet(decisoes_fts, 2, '[', ']', '...', 30) AS contexto
FROM decisoes_fts
JOIN decisoes d ON d.rowid = decisoes_fts.rowid
WHERE decisoes_fts MATCH 'NEAR(reincidencia agravante, 15)';


-- ----------------------------------------------------------------------------
-- 6. ESTATÍSTICA AGREGADA POR ANO DE PUBLICAÇÃO (SÉRIE HISTÓRICA)
-- O que faz: Agrupa as decisões por ano, contabilizando o volume total de
-- julgados, quantos possuem multa pecuniária extraída, o valor total somado,
-- a média aritmética, o menor e o maior valor de multa aplicados em cada ano.
-- ----------------------------------------------------------------------------
SELECT
    COALESCE(CAST(ano_publicacao AS TEXT), 'Sem ano identificado') AS ano,
    COUNT(*) AS total_decisoes,
    COUNT(multa_principal_num) AS qtd_com_multa,
    ROUND(COALESCE(SUM(multa_principal_num), 0), 2) AS soma_multas_brl,
    ROUND(COALESCE(AVG(multa_principal_num), 0), 2) AS media_multa_brl,
    ROUND(MIN(multa_principal_num), 2) AS menor_multa_brl,
    ROUND(MAX(multa_principal_num), 2) AS maior_multa_brl
FROM decisoes
GROUP BY ano_publicacao
ORDER BY ano_publicacao ASC;


-- ----------------------------------------------------------------------------
-- 7. ESTATÍSTICA AGREGADA POR CLASSIFICAÇÃO DA INFRAÇÃO (LEI Nº 6.437/1977)
-- O que faz: Agrupa as decisões pela gravidade extraída (Leve, Grave,
-- Gravíssima ou combinações), apresentando a contagem de processos, a soma
-- financeira das sanções e a média da multa por categoria de gravidade.
-- ----------------------------------------------------------------------------
SELECT
    classificacao_infracao,
    COUNT(*) AS total_decisoes,
    COUNT(multa_principal_num) AS qtd_com_multa,
    ROUND(COALESCE(SUM(multa_principal_num), 0), 2) AS soma_multas_brl,
    ROUND(COALESCE(AVG(multa_principal_num), 0), 2) AS media_multa_brl,
    ROUND(MIN(multa_principal_num), 2) AS menor_multa_brl,
    ROUND(MAX(multa_principal_num), 2) AS maior_multa_brl
FROM decisoes
GROUP BY classificacao_infracao
ORDER BY total_decisoes DESC;


-- ----------------------------------------------------------------------------
-- 8. TABELA CRUZADA: ANO X CLASSIFICAÇÃO DA INFRAÇÃO (EVOLUÇÃO DA DOSIMETRIA)
-- O que faz: Combina o recorte temporal (ano) com a gravidade da infração,
-- permitindo observar como a quantidade de decisões e o ticket médio das
-- multas leves, graves e gravíssimas evoluíram ao longo dos anos.
-- ----------------------------------------------------------------------------
SELECT
    COALESCE(CAST(ano_publicacao AS TEXT), 'Sem ano') AS ano,
    classificacao_infracao,
    COUNT(*) AS total_decisoes,
    COUNT(multa_principal_num) AS qtd_com_multa,
    ROUND(COALESCE(SUM(multa_principal_num), 0), 2) AS soma_multas_brl,
    ROUND(COALESCE(AVG(multa_principal_num), 0), 2) AS media_multa_brl
FROM decisoes
GROUP BY ano_publicacao, classificacao_infracao
ORDER BY ano_publicacao ASC, total_decisoes DESC;