import re
import sqlite3
from pathlib import Path

from openpyxl import Workbook
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter

from config import BASE_DIR
from extractor import INCISOS_ART10_LISTA

DB_PATH = BASE_DIR / "anvisa_decisoes.db"
SQL_PATH = BASE_DIR / "consultas_tese.sql"
XLSX_PATH = BASE_DIR / "relatorio_consultas_tese.xlsx"

# Regex para remover caracteres de controle ilegais no XML do Excel (comuns em PDFs antigos)
REGEX_CHAR_ILEGAL = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f]")


def limpar_valor_excel(valor):
    """Remove caracteres de controle invisíveis que quebram a geração do .xlsx."""
    if isinstance(valor, str):
        return REGEX_CHAR_ILEGAL.sub("", valor)
    return valor


def extrair_consultas_do_arquivo(caminho_sql: Path) -> list[tuple[str, str]]:
    """
    Lê o arquivo consultas_tese.sql, extrai o título de cada bloco comentado
    (ex: '-- 9. ESTATÍSTICA AGREGADA POR ORIGEM...') e a respectiva instrução SQL.
    """
    conteudo = caminho_sql.read_text(encoding="utf-8")
    blocos_brutos = [b.strip() for b in conteudo.split(";") if b.strip()]
    consultas = []

    for idx, bloco in enumerate(blocos_brutos, start=1):
        linhas = bloco.splitlines()
        titulo_aba = f"Consulta_{idx}"
        linhas_sql = []

        for linha in linhas:
            linha_strip = linha.strip()
            match_titulo = re.match(r"^--\s*(\d+\.\s*.+)$", linha_strip)
            if match_titulo:
                titulo_aba = match_titulo.group(1)

            if linha_strip and not linha_strip.startswith("--"):
                linhas_sql.append(linha)

        sql_limpo = "\n".join(linhas_sql).strip()
        if sql_limpo:
            nome_aba_seguro = re.sub(r"[\\/*?:\[\]]", "-", titulo_aba)[:31].strip()
            consultas.append((nome_aba_seguro, sql_limpo))

    return consultas


def obter_base_completa_com_incisos(cursor: sqlite3.Cursor) -> tuple[list[str], list[list]]:
    """
    Monta a matriz completa de decisões com todos os novos campos + as 42 colunas
    binárias (0/1) dos incisos do Art. 10 para contagem e soma automática no Excel.
    """
    colunas_base = [
        "item_id",
        "arquivo_rastreio",
        "titulo",
        "data_assinatura",
        "data_publicacao",
        "ano_publicacao",
        "autor",
        "origem_ais",
        "risco",
        "primariedade",
        "porte",
        "classificacao_infracao",
        "valor_multa_raw",
        "multa_principal_num",
        "incisos_art_10_raw",
        "total_incisos_art10",
        "url_pdf",
    ]
    colunas_incisos = [f"Art10_{inc}" for inc in INCISOS_ART10_LISTA]
    todas_colunas = colunas_base + colunas_incisos

    # Carrega mapa de incisos por item_id em memória para montagem rápida
    cursor.execute("SELECT item_id, inciso FROM decisao_incisos")
    mapa_incisos: dict[str, set[str]] = {}
    for item_id, inciso in cursor.fetchall():
        mapa_incisos.setdefault(item_id, set()).add(inciso)

    cursor.execute(f"SELECT {', '.join(colunas_base)} FROM decisoes ORDER BY ano_publicacao ASC, item_id ASC")
    linhas_resultado = []

    for row in cursor.fetchall():
        item_id = row[0]
        incisos_do_item = mapa_incisos.get(item_id, set())
        flags_binarias = [1 if inc in incisos_do_item else 0 for inc in INCISOS_ART10_LISTA]
        linhas_resultado.append(list(row) + flags_binarias)

    return todas_colunas, linhas_resultado


def formatar_planilha(ws, colunas: list[str], linhas_dados: list[list | tuple]):
    """Aplica estilização, formatação monetária/numérica, filtros e ajuste de largura."""
    fonte_cabecalho = Font(name="Calibri", size=11, bold=True, color="FFFFFF")
    preenchimento_cabecalho = PatternFill(start_color="1F4E78", end_color="1F4E78", fill_type="solid")
    alinhamento_cabecalho = Alignment(horizontal="left", vertical="center", wrap_text=True)
    alinhamento_centro = Alignment(horizontal="center", vertical="center")

    ws.append(colunas)
    for col_idx, col_nome in enumerate(colunas, start=1):
        celula = ws.cell(row=1, column=col_idx)
        celula.font = fonte_cabecalho
        celula.fill = preenchimento_cabecalho
        celula.alignment = alinhamento_centro if col_nome.startswith("Art10_") else alinhamento_cabecalho

    # Insere os dados sanitizados
    for linha in linhas_dados:
        ws.append([limpar_valor_excel(v) for v in linha])

    # Aplica formatos numéricos/monetários por tipo de coluna
    total_linhas = len(linhas_dados) + 1
    for col_idx, col_nome in enumerate(colunas, start=1):
        col_lower = col_nome.lower()
        eh_moeda = col_lower.endswith("_brl") or col_lower == "multa_principal_num"
        eh_binario_inciso = col_nome.startswith("Art10_")
        eh_inteiro = col_lower in ("total_decisoes", "qtd_com_multa", "total_incisos_art10")

        if eh_moeda or eh_binario_inciso or eh_inteiro:
            for row_idx in range(2, total_linhas + 1):
                celula = ws.cell(row=row_idx, column=col_idx)
                if eh_moeda and isinstance(celula.value, (int, float)):
                    celula.number_format = 'R$ #,##0.00'
                elif eh_binario_inciso:
                    celula.number_format = "0"
                    celula.alignment = alinhamento_centro
                elif eh_inteiro and isinstance(celula.value, (int, float)):
                    celula.number_format = "#,##0"

    # Congela a primeira linha e ativa filtros
    ws.freeze_panes = "A2"
    if linhas_dados:
        ws.auto_filter.ref = ws.dimensions

    # Ajusta a largura das colunas
    for col_idx, col_nome in enumerate(colunas, start=1):
        letra_col = get_column_letter(col_idx)

        if col_nome.startswith("Art10_"):
            ws.column_dimensions[letra_col].width = 10
            continue

        maior_tamanho = len(str(col_nome))
        for row_idx in range(2, min(total_linhas + 1, 200)):
            valor = ws.cell(row=row_idx, column=col_idx).value
            if valor is not None:
                maior_tamanho = max(maior_tamanho, len(str(valor)))

        ws.column_dimensions[letra_col].width = min(maior_tamanho + 4, 60)


def exportar_para_excel():
    if not DB_PATH.exists():
        print(f"Erro: Banco de dados não encontrado em {DB_PATH}. Rode 'python importar_sqlite.py' primeiro.")
        return

    if not SQL_PATH.exists():
        print(f"Erro: Arquivo SQL não encontrado em {SQL_PATH}.")
        return

    consultas = extrair_consultas_do_arquivo(SQL_PATH)
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    wb = Workbook()
    wb.remove(wb.active)

    # 1. Cria a aba principal com a Base Completa + 42 colunas individuais de incisos
    print(f"Gerando aba '0. BASE COMPLETA' a partir de {DB_PATH.name}...")
    try:
        colunas_base, linhas_base = obter_base_completa_com_incisos(cursor)
        ws_base = wb.create_sheet(title="0. BASE COMPLETA")
        formatar_planilha(ws_base, colunas_base, linhas_base)
        print(f"[OK] Aba '0. BASE COMPLETA' criada ({len(linhas_base)} registros, {len(colunas_base)} colunas).")
    except Exception as e:
        print(f"[ERRO] Falha ao gerar aba '0. BASE COMPLETA': {e}")

    # 2. Cria uma aba para cada consulta do consultas_tese.sql
    print(f"\nExecutando {len(consultas)} consultas de {SQL_PATH.name}...")
    for nome_aba, query_sql in consultas:
        try:
            cursor.execute(query_sql)
            linhas = cursor.fetchall()
            colunas = [desc[0] for desc in cursor.description] if cursor.description else []

            ws = wb.create_sheet(title=nome_aba)
            formatar_planilha(ws, colunas, linhas)
            print(f"[OK] Aba '{nome_aba}' criada ({len(linhas)} registros).")

        except Exception as e:
            print(f"[ERRO] Falha ao executar '{nome_aba}': {e}")

    conn.close()
    wb.save(XLSX_PATH)
    print(f"\n=== Exportação Concluída! ===")
    print(f"Planilha gerada em: {XLSX_PATH}")


if __name__ == "__main__":
    exportar_para_excel()