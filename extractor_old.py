'''
Converte o PDF em .txt utilizando PyMuPDF (fitz) e aplica expressões regulares desenhadas especificamente para o padrão de redação dos votos, decisões da GGREC/DIRETORIA e autos de infração sanitária da ANVISA (baseados na Lei nº 6.437/1977).
'''

import re
from pathlib import Path

from pypdf import PdfReader

from config import registrar_falha


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


def extrair_valor_multa(texto: str) -> str:
    """
    5.1. Extrai o valor da multa aplicada.
    Prioriza trechos próximos à palavra 'multa' (ex: 'multa no valor de R$ 15.000,00' ou 'dobrada para R$ ...').
    Se houver múltiplos valores (ex: multa inicial e multa reduzida/dobrada em recurso), retorna todos separados por ' | '.
    """
    if not texto:
        return "Não identificado"

    # Normaliza quebras de linha e espaços múltiplos para facilitar busca em frases quebradas
    texto_limpo = re.sub(r"\s+", " ", texto)

    # Padrão 1: Contexto direto de multa (até 80 caracteres entre a palavra 'multa' e a cifra 'R$')
    padrao_contextual = re.compile(
        r"(?:multa|penalidade pecuni[áa]ria|valor)[^R\$]{0,80}?R\$\s*(\d{1,3}(?:\.\d{3})*,\d{2})",
        re.IGNORECASE,
    )
    matches = padrao_contextual.findall(texto_limpo)

    if not matches:
        # Padrão 2: Busca geral por valores monetários em Reais no documento
        padrao_geral = re.compile(r"R\$\s*(\d{1,3}(?:\.\d{3})*,\d{2})")
        matches = padrao_geral.findall(texto_limpo)

    if matches:
        # Remove duplicatas mantendo a ordem de aparição no documento
        valores_unicos = list(dict.fromkeys([f"R$ {v}" for v in matches]))
        return " | ".join(valores_unicos)

    return "Sem multa pecuniária / Não encontrado"


def extrair_classificacao_infracao(texto: str) -> str:
    """
    5.2. Extrai a classificação da infração (leve, grave, gravíssima).
    Procura primeiro no contexto de 'infração sanitária / natureza / classificada como',
    com fallback para menções diretas aos termos da Lei 6.437/77.
    """
    if not texto:
        return "Não identificado"

    texto_limpo = re.sub(r"\s+", " ", texto)

    # Padrão contextual próximo a palavras-chave jurídicas da ANVISA
    padrao_contexto = re.compile(
        r"(?:infra[çc][ãa]o|natureza|classifica[çc][ãa]o|classificada como|grau)[^.;:]{0,60}?\b(grav[íi]ssima|grave|leve)s?\b",
        re.IGNORECASE,
    )
    encontrados = [m.lower() for m in padrao_contexto.findall(texto_limpo)]

    if not encontrados:
        # Fallback: busca a presença dos termos isolados caso a frase esteja invertida
        padrao_direto = re.compile(r"\b(grav[íi]ssima|grave|leve)s?\b", re.IGNORECASE)
        encontrados = [m.lower() for m in padrao_direto.findall(texto_limpo)]

    if encontrados:
        # Normaliza acentuação e remove duplicatas
        normalizados = []
        for item in encontrados:
            termo = "gravíssima" if item.startswith("graví") or item.startswith("gravi") else item
            if termo.capitalize() not in normalizados:
                normalizados.append(termo.capitalize())
        return ", ".join(normalizados)

    return "Não encontrado"


def extrair_incisos_art10(texto: str) -> str:
    """
    5.3. Extrai os incisos (em algarismos romanos) do Art. 10 da Lei nº 6.437/1977 imputados.
    Suporta variações comuns nos textos da ANVISA:
    - 'art. 10, inciso IV e XXIX'
    - 'artigo 10, IV, da Lei 6.437/77'
    - 'incisos I, IV e XXXI do art. 10'
    """
    if not texto:
        return "Não identificado"

    texto_limpo = re.sub(r"\s+", " ", texto)
    incisos_encontrados = []

    # Regex para validar algarismos romanos de I a XLII (o Art. 10 da Lei 6.437/77 possui 42 incisos)
    regex_romano = r"\b(XL|XLI|XLII|XXX[I]{0,3}|XX[I]{0,3}|X[I]{0,3}|IX|IV|V?[I]{1,3}|V|X)\b"

    # Padrão A: "art. 10" ou "artigo 10" seguido dos incisos nos próximos 120 caracteres
    padrao_pos_art10 = re.compile(
        r"art(?:igo|\.)?\s*10\b([^.;]{1,120})",
        re.IGNORECASE,
    )
    for trecho in padrao_pos_art10.findall(texto_limpo):
        romanos = re.findall(regex_romano, trecho)
        for r in romanos:
            if r not in incisos_encontrados:
                incisos_encontrados.append(r)

    # Padrão B: "inciso(s) X, Y do art. 10" (quando o inciso vem antes da menção ao artigo 10)
    padrao_pre_art10 = re.compile(
        r"incisos?\s+([^.;]{1,80}?)\s+do\s+art(?:igo|\.)?\s*10\b",
        re.IGNORECASE,
    )
    for trecho in padrao_pre_art10.findall(texto_limpo):
        romanos = re.findall(regex_romano, trecho)
        for r in romanos:
            if r not in incisos_encontrados:
                incisos_encontrados.append(r)

    if incisos_encontrados:
        return ", ".join(incisos_encontrados)

    return "Não encontrado"


def extrair_dados_decisao(texto: str) -> dict:
    """Executa as três extrações sobre o texto do PDF convertido."""
    return {
        "valor_multa": extrair_valor_multa(texto),
        "classificacao_infracao": extrair_classificacao_infracao(texto),
        "incisos_art_10": extrair_incisos_art10(texto),
    }