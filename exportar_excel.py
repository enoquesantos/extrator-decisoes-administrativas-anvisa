import re
import sqlite3
from pathlib import Path

from openpyxl import Workbook
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter

from config import BASE_DIR

DB_PATH = BASE_DIR / "anvisa_decisoes.db"
SQL_PATH = BASE_DIR / "consultas_tese.sql"
XLSX_PATH = BASE_DIR / "relatorio_consultas_tese.xlsx"


def extrair_consultas_do_arquivo(caminho_sql: Path) -> list[tuple[str, str]]:
    """
    Lê o arquivo consultas_tese.sql, extrai o título de cada bloco comentado
    (ex: '-- 1. FILTRO POR GRAVIDADE...') e a respectiva instrução SQL.
    Retorna uma lista de tuplas: (nome_da_aba, comando_sql).
    """
    conteudo = caminho_sql.read_text(encoding="utf-8")

    # Divide o arquivo pelos pontos-e-vírgula que encerram cada query
    blocos_brutos = [b.strip() for b in conteudo.split(";") if b.strip()]
    consultas = []

    for idx, bloco in enumerate(blocos_brutos, start=1):
        linhas = bloco.splitlines()
        titulo_aba = f"Consulta_{idx}"
        linhas_sql = []

        for linha in linhas:
            linha_strip = linha.strip()
            # Captura a linha de título numerado no comentário (ex: "-- 1. FILTRO...")
            match_titulo = re.match(r"^--\s*(\d+\.\s*.+)$", linha_strip)
            if match_titulo:
                titulo_aba = match_titulo.group(1)

            # Mantém apenas as linhas SQL reais (ignora comentários e linhas vazias)
            if linha_strip and not linha_strip.startswith("--"):
                linhas_sql.append(linha)

        sql_limpo = "\n".join(linhas_sql).strip()
        if sql_limpo:
            # Limpa caracteres inválidos para nomes de aba no Excel e respeita o limite de 31 chars
            nome_aba_seguro = re.sub(r"[\\/*?:\[\]]", "-", titulo_aba)[:31].strip()
            consultas.append((nome_aba_seguro, sql_limpo))

    return consultas


def formatar_planilha(ws, colunas: list[str], linhas_dados: list[tuple]):
    """Aplica estilização profissional (cabeçalho escuro, auto-filtro e largura automática)."""
    # Estilo do cabeçalho
    fonte_cabecalho = Font(name="Calibri", size=11, bold=True, color="FFFFFF")
    preenchimento_cabecalho = PatternFill(start_color="1F4E78", end_color="1F4E78", fill_type="solid")
    alinhamento_cabecalho = Alignment(horizontal="left", vertical="center", wrap_text=True)

    ws.append(colunas)
    for col_idx in range(1, len(colunas) + 1):
        celula = ws.cell(row=1, column=col_idx)
        celula.font = fonte_cabecalho
        celula.fill = preenchimento_cabecalho
        celula.alignment = alinhamento_cabecalho

    # Insere os dados retornados pelo SQLite
    for linha in linhas_dados:
        ws.append(list(linha))

    # Congela a primeira linha e ativa filtros nas colunas
    ws.freeze_panes = "A2"
    if linhas_dados:
        ws.auto_filter.ref = ws.dimensions

    # Ajusta a largura das colunas (com teto de 60 caracteres para textos longos/snippets)
    for col_idx, col_nome in enumerate(colunas, start=1):
        letra_col = get_column_letter(col_idx)
        maior_tamanho = len(str(col_nome))

        for row_idx in range(2, min(len(linhas_dados) + 2, 200)):  # Amostra até 200 linhas para rapidez
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
    if not consultas:
        print("Nenhuma consulta válida encontrada no arquivo SQL.")
        return

    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    wb = Workbook()
    # Remove a aba padrão em branco criada pelo openpyxl
    wb.remove(wb.active)

    print(f"Executando {len(consultas)} consultas em {DB_PATH.name}...")

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
