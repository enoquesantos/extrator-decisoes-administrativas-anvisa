import re
from pathlib import Path

from pypdf import PdfReader

from config import registrar_falha

# Todos os 42 incisos do Art. 10 da Lei nº 6.437/1977 em ordem
INCISOS_ART10_LISTA = [
    "I", "II", "III", "IV", "V", "VI", "VII", "VIII", "IX", "X",
    "XI", "XII", "XIII", "XIV", "XV", "XVI", "XVII", "XVIII", "XIX", "XX",
    "XXI", "XXII", "XXIII", "XXIV", "XXV", "XXVI", "XXVII", "XXVIII", "XXIX", "XXX",
    "XXXI", "XXXII", "XXXIII", "XXXIV", "XXXV", "XXXVI", "XXXVII", "XXXVIII", "XXXIX", "XL",
    "XLI", "XLII",
]

MESES_PT = {
    "janeiro": "01", "fevereiro": "02", "março": "03", "marco": "03",
    "abril": "04", "maio": "05", "junho": "06", "julho": "07",
    "agosto": "08", "setembro": "09", "outubro": "10",
    "novembro": "11", "dezembro": "12",
}


def converter_pdf_para_txt(caminho_pdf: Path, caminho_txt: Path, item_id: str, url_pdf: str) -> str | None:
    """
    Abre o PDF usando pypdf, extrai o texto de todas as páginas, salva em arquivo .txt
    e retorna a string completa. Se o PDF estiver corrompido, registra no log.
    """
    try:
        leitor = PdfReader(caminho_pdf)
        paginas_texto = []

        for pagina in leitor.pages:
            texto_pagina = pagina.extract_text()
            if texto_pagina:
                paginas_texto.append(texto_pagina)

        texto_completo = "\n".join(paginas_texto).strip()

        if not texto_completo:
            registrar_falha(
                item_id,
                url_pdf,
                "PDF aberto com sucesso, mas não contém camada de texto extraível (possível imagem/scan sem OCR).",
            )
            caminho_txt.write_text("", encoding="utf-8")
            return ""

        caminho_txt.write_text(texto_completo, encoding="utf-8")
        return texto_completo

    except Exception as e:
        registrar_falha(item_id, url_pdf, f"PDF corrompido ou erro de leitura no pypdf: {str(e)}")
        return None


def extrair_data_assinatura(texto: str) -> str:
    """
    Extrai a data da assinatura no final da página/documento (carimbo SEI ou fecho datado).
    Retorna no formato DD/MM/AAAA.
    """
    if not texto:
        return "Não encontrado"

    # Foca nos últimos 2000 caracteres do documento (onde fica a assinatura)
    trecho_final = re.sub(r"\s+", " ", texto[-2000:])

    # Padrão 1: Carimbo de assinatura eletrônica (SEI) - ex: "em 14/05/2021, às 16:30"
    padrao_sei = re.compile(
        r"(?:assinado\s+eletronicamente|assinatura)[^0-9]{0,120}?em\s+(\d{2}/\d{2}/\d{4})",
        re.IGNORECASE,
    )
    matches_sei = padrao_sei.findall(trecho_final)
    if matches_sei:
        return matches_sei[-1]  # Pega a última assinatura do documento

    # Padrão 2: Data por extenso no fecho - ex: "Brasília, 15 de agosto de 2022"
    padrao_extenso = re.compile(
        r"(\d{1,2})\s+de\s+(janeiro|fevereiro|mar[çc]o|abril|maio|junho|julho|agosto|setembro|outubro|novembro|dezembro)\s+de\s+(\d{4})",
        re.IGNORECASE,
    )
    matches_extenso = padrao_extenso.findall(trecho_final)
    if matches_extenso:
        dia, mes_nome, ano = matches_extenso[-1]
        mes_num = MESES_PT.get(mes_nome.lower(), "00")
        return f"{int(dia):02d}/{mes_num}/{ano}"

    # Padrão 3: Fallback para a última data DD/MM/AAAA presente no trecho final
    matches_data = re.findall(r"\b(\d{2}/\d{2}/(?:19|20)\d{2})\b", trecho_final)
    if matches_data:
        return matches_data[-1]

    return "Não encontrado"


def extrair_origem_ais(texto: str) -> str:
    """
    Extrai o código de origem do AIS em posição fixa após o hífen no número do AIS.
    Exemplos suportados:
    - AIS nº 123456/20-5 - GGFIS-DF
    - Auto de Infração Sanitária nº 0123/2019-PVPAF
    - AIS 045/2021 - CMPAF / COPAS
    """
    if not texto:
        return "Não encontrado"

    texto_limpo = re.sub(r"\s+", " ", texto)

    # Busca menção a AIS / Auto de Infração seguida de numeração e hífen + sigla em maiúsculas
    padrao_ais = re.compile(
        r"(?:AIS|Auto\s+de\s+Infra[çc][ãa]o(?:\s+Sanit[áa]ria)?)\s*(?:n[º°o\.]*)?\s*[\d\./\-]+?\s*[-–—]\s*([A-Z]{2,10}(?:-[A-Z]{2,5})?)\b"
    )
    match = padrao_ais.search(texto_limpo)
    if match:
        return match.group(1).strip()

    # Fallback: busca padrão de número de AIS colado ao hífen (ex: 123456/20-GGFIS-DF ou 123/2020-PVPAF)
    padrao_fallback = re.compile(
        r"\b\d{1,7}/\d{2,4}(?:-\d)?\s*[-–—]\s*([A-Z]{3,10}(?:-[A-Z]{2,5})?)\b"
    )
    match_fb = padrao_fallback.search(texto_limpo)
    if match_fb:
        return match_fb.group(1).strip()

    return "Não encontrado"


def extrair_risco(texto: str) -> str:
    """
    Extrai o nível de risco sanitário: Baixo, Médio, Alto ou Muito Alto.
    Verifica 'muito alto' antes de 'alto' para evitar falso positivo.
    """
    if not texto:
        return "Não encontrado"

    texto_limpo = re.sub(r"\s+", " ", texto)

    # Busca no contexto próximo à palavra "risco" (ex: "risco sanitário alto", "classificado como risco muito alto")
    padrao_risco = re.compile(
        r"risco(?:\s+sanit[áa]rio)?[^.;:]{0,45}?\b(muito\s+alto|alto|m[ée]dio|baixo)\b",
        re.IGNORECASE,
    )
    match = padrao_risco.search(texto_limpo)
    if not match:
        # Ordem inversa: ex: "alto risco sanitário", "muito alto risco"
        padrao_inverso = re.compile(
            r"\b(muito\s+alto|alto|m[ée]dio|baixo)\s+risco\b",
            re.IGNORECASE,
        )
        match = padrao_inverso.search(texto_limpo)

    if match:
        valor = re.sub(r"\s+", " ", match.group(1).lower().strip())
        mapa = {
            "baixo": "Baixo",
            "médio": "Médio",
            "medio": "Médio",
            "alto": "Alto",
            "muito alto": "Muito Alto",
        }
        return mapa.get(valor, valor.title())

    return "Não encontrado"


def extrair_primariedade(texto: str) -> str:
    """
    Identifica se o autuado é 'Reincidente' ou 'Primário'.
    Busca primeiro por 'reincidente' (filtrando contextos negativos como 'não reincidente'),
    pois a palavra 'primária' pode aparecer em frases negativas ('não é primária').
    """
    if not texto:
        return "Não encontrado"

    texto_limpo = re.sub(r"\s+", " ", texto)

    # 1. Verifica explicitamente se há negação de reincidência (indica Primário)
    padrao_nao_reincidente = re.compile(
        r"\b(?:n[ãa]o\s+(?:[ée]\s+|consta\s+como\s+|se\s+trata\s+de\s+)?reincidente|aus[êe]ncia\s+de\s+reincid[êe]ncia|sem\s+reincid[êe]ncia)\b",
        re.IGNORECASE,
    )
    if padrao_nao_reincidente.search(texto_limpo):
        return "Primário"

    # 2. Busca por 'reincidente' ou 'reincidência' em contexto afirmativo
    padrao_reincidente = re.compile(
        r"(?<!n[ãa]o\s)(?<!sem\s)\b(reincidente|reincid[êe]ncia\s+(?:espec[íi]fica|gen[ée]rica|comprovada|constatada))\b",
        re.IGNORECASE,
    )
    if padrao_reincidente.search(texto_limpo):
        return "Reincidente"

    # 3. Se não for reincidente, verifica menção a primário/primária/primariedade
    padrao_primario = re.compile(
        r"(?<!n[ãa]o\s)\b(prim[áa]ri[oa]|primariedade)\b",
        re.IGNORECASE,
    )
    if padrao_primario.search(texto_limpo):
        return "Primário"

    return "Não encontrado"


def extrair_porte(texto: str) -> str:
    """
    Extrai o porte econômico especificamente da seção de dosimetria da pena/multa,
    evitando menções anteriores no relatório.
    Retorna: PF, Microempresa, Empresa de Pequeno Porte, Médio Porte Grupo III/IV, Grande Porte Grupo I/II, etc.
    """
    if not texto:
        return "Não encontrado"

    texto_limpo = re.sub(r"\s+", " ", texto)

    # Isola o trecho a partir da seção de dosimetria (pega a última ocorrência se houver mais de uma)
    matches_dosimetria = list(
        re.finditer(r"\b(?:dosimetria|da\s+penalidade|da\s+fixa[çc][ãa]o\s+da\s+multa)\b", texto_limpo, re.IGNORECASE)
    )
    if matches_dosimetria:
        trecho_alvo = texto_limpo[matches_dosimetria[-1].start():]
    else:
        # Fallback: usa a segunda metade do documento (onde normalmente está a fundamentação da multa)
        trecho_alvo = texto_limpo[len(texto_limpo) // 2:]

    # Ordem de especificidade (do mais específico para o mais genérico)
    padroes_porte = [
        (r"\bgrande\s+porte\s*[-–,]?\s*grupo\s*(I{1,2})\b", lambda m: f"Grande Porte Grupo {m.group(1).upper()}"),
        (r"\bm[ée]dio\s+porte\s*[-–,]?\s*grupo\s*(III|IV)\b", lambda m: f"Médio Porte Grupo {m.group(1).upper()}"),
        (r"\bgrupo\s*(I{1,2})\s*[-–,]?\s*grande\s+porte\b", lambda m: f"Grande Porte Grupo {m.group(1).upper()}"),
        (r"\bgrupo\s*(III|IV)\s*[-–,]?\s*m[ée]dio\s+porte\b", lambda m: f"Médio Porte Grupo {m.group(1).upper()}"),
        (r"\bgrande\s+porte\b", lambda m: "Grande Porte"),
        (r"\bm[ée]dio\s+porte\b", lambda m: "Médio Porte"),
        (r"\bempresa\s+de\s+pequeno\s+porte\b|\bEPP\b", lambda m: "Empresa de Pequeno Porte"),
        (r"\bmicroempresa\b|\bmicro\s+empresa\b", lambda m: "Microempresa"),
        (r"\bpessoa\s+f[íi]sica\b|\bporte\s*[:\-]?\s*PF\b", lambda m: "PF"),
    ]

    for regex, formatador in padroes_porte:
        match = re.search(regex, trecho_alvo, re.IGNORECASE)
        if match:
            return formatador(match)

    return "Não encontrado"


def extrair_valor_multa(texto: str) -> str:
    """Extrai o valor da multa aplicada em Reais."""
    if not texto:
        return "Não identificado"

    texto_limpo = re.sub(r"\s+", " ", texto)

    padrao_contextual = re.compile(
        r"(?:multa|penalidade pecuni[áa]ria|valor)[^R\$]{0,80}?R\$\s*(\d{1,3}(?:\.\d{3})*,\d{2})",
        re.IGNORECASE,
    )
    matches = padrao_contextual.findall(texto_limpo)

    if not matches:
        padrao_geral = re.compile(r"R\$\s*(\d{1,3}(?:\.\d{3})*,\d{2})")
        matches = padrao_geral.findall(texto_limpo)

    if matches:
        valores_unicos = list(dict.fromkeys([f"R$ {v}" for v in matches]))
        return " | ".join(valores_unicos)

    return "Sem multa pecuniária / Não encontrado"


def extrair_classificacao_infracao(texto: str) -> str:
    """Extrai a classificação da infração (Leve, Grave, Gravíssima)."""
    if not texto:
        return "Não identificado"

    texto_limpo = re.sub(r"\s+", " ", texto)

    padrao_contexto = re.compile(
        r"(?:infra[çc][ãa]o|natureza|classifica[çc][ãa]o|classificada como|grau)[^.;:]{0,60}?\b(grav[íi]ssima|grave|leve)s?\b",
        re.IGNORECASE,
    )
    encontrados = [m.lower() for m in padrao_contexto.findall(texto_limpo)]

    if not encontrados:
        padrao_direto = re.compile(r"\b(grav[íi]ssima|grave|leve)s?\b", re.IGNORECASE)
        encontrados = [m.lower() for m in padrao_direto.findall(texto_limpo)]

    if encontrados:
        normalizados = []
        for item in encontrados:
            termo = "gravíssima" if item.startswith("graví") or item.startswith("gravi") else item
            if termo.capitalize() not in normalizados:
                normalizados.append(termo.capitalize())
        return ", ".join(normalizados)

    return "Não encontrado"


def extrair_incisos_art10(texto: str) -> tuple[list[str], dict[str, int]]:
    """
    Extrai os incisos do Art. 10 da Lei nº 6.437/1977.
    Retorna:
      1. Lista de incisos encontrados (ex: ['IV', 'XXIX'])
      2. Dicionário binário para as 42 colunas (ex: {'Art10_I': 0, ..., 'Art10_IV': 1, ...})
    """
    colunas_incisos = {f"Art10_{inc}": 0 for inc in INCISOS_ART10_LISTA}

    if not texto:
        return [], colunas_incisos

    texto_limpo = re.sub(r"\s+", " ", texto)
    incisos_encontrados = []

    regex_romano = r"\b(XLII|XLI|XL|XXXIX|XXXVIII|XXXVII|XXXVI|XXXV|XXXIV|XXXIII|XXXII|XXXI|XXX|XXIX|XXVIII|XXVII|XXVI|XXV|XXIV|XXIII|XXII|XXI|XX|XIX|XVIII|XVII|XVI|XV|XIV|XIII|XII|XI|X|IX|VIII|VII|VI|V|IV|III|II|I)\b"

    padrao_pos_art10 = re.compile(r"art(?:igo|\.)?\s*10\b([^.;]{1,120})", re.IGNORECASE)
    for trecho in padrao_pos_art10.findall(texto_limpo):
        for r in re.findall(regex_romano, trecho):
            if r in INCISOS_ART10_LISTA and r not in incisos_encontrados:
                incisos_encontrados.append(r)

    padrao_pre_art10 = re.compile(r"incisos?\s+([^.;]{1,80}?)\s+do\s+art(?:igo|\.)?\s*10\b", re.IGNORECASE)
    for trecho in padrao_pre_art10.findall(texto_limpo):
        for r in re.findall(regex_romano, trecho):
            if r in INCISOS_ART10_LISTA and r not in incisos_encontrados:
                incisos_encontrados.append(r)

    for inc in incisos_encontrados:
        colunas_incisos[f"Art10_{inc}"] = 1

    return incisos_encontrados, colunas_incisos


def extrair_dados_decisao(texto: str) -> dict:
    """Executa todas as extrações sobre o texto do PDF convertido."""
    lista_incisos, colunas_incisos = extrair_incisos_art10(texto)

    dados = {
        "data_assinatura": extrair_data_assinatura(texto),
        "origem_ais": extrair_origem_ais(texto),
        "risco": extrair_risco(texto),
        "primariedade": extrair_primariedade(texto),
        "porte": extrair_porte(texto),
        "valor_multa": extrair_valor_multa(texto),
        "classificacao_infracao": extrair_classificacao_infracao(texto),
        "incisos_art_10": ", ".join(lista_incisos) if lista_incisos else "Não encontrado",
        "total_incisos_art_10": len(lista_incisos),
    }
    dados.update(colunas_incisos)
    return dados