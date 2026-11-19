import csv
import re
import sqlite3
from pathlib import Path

from config import BASE_DIR, OUTPUT_DIR

DB_PATH = BASE_DIR / "anvisa_decisoes.db"


def parse_valor_monetario(valor_str: str) -> float | None:
    if not valor_str:
        return None
    match = re.search(r"R\$\s*(\d{1,3}(?:\.\d{3})*,\d{2})", valor_str)
    if not match:
        return None
    numero_limpo = match.group(1).replace(".", "").replace(",", ".")
    try:
        return float(numero_limpo)
    except ValueError:
        return None


def extrair_ano(data_str: str) -> int | None:
    if not data_str:
        return None
    match = re.search(r"\b(19\d{2}|20\d{2})\b", data_str)
    return int(match.group(1)) if match else None


def inicializar_banco(conn: sqlite3.Connection):
    cursor = conn.cursor()

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS decisoes (
            item_id TEXT PRIMARY KEY,
            arquivo_rastreio TEXT NOT NULL,
            titulo TEXT,
            data_assinatura TEXT,
            data_publicacao TEXT,
            ano_publicacao INTEGER,
            autor TEXT,
            url_pdf TEXT,
            origem_ais TEXT,
            risco TEXT,
            primariedade TEXT,
            porte TEXT,
            valor_multa_raw TEXT,
            multa_principal_num REAL,
            classificacao_infracao TEXT,
            incisos_art_10_raw TEXT,
            total_incisos_art10 INTEGER,
            texto_completo TEXT,
            caminho_pasta TEXT
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS decisao_incisos (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            item_id TEXT NOT NULL,
            inciso TEXT NOT NULL,
            FOREIGN KEY (item_id) REFERENCES decisoes(item_id) ON DELETE CASCADE,
            UNIQUE(item_id, inciso)
        )
    """)

    cursor.execute("""
        CREATE VIRTUAL TABLE IF NOT EXISTS decisoes_fts USING fts5(
            item_id UNINDEXED,
            titulo,
            texto_completo,
            content='decisoes',
            content_rowid='rowid',
            tokenize='unicode61 remove_diacritics 2'
        )
    """)

    cursor.execute("""
        CREATE TRIGGER IF NOT EXISTS decisoes_ai AFTER INSERT ON decisoes BEGIN
            INSERT INTO decisoes_fts(rowid, item_id, titulo, texto_completo)
            VALUES (new.rowid, new.item_id, new.titulo, new.texto_completo);
        END;
    """)

    cursor.execute("""
        CREATE TRIGGER IF NOT EXISTS decisoes_ad AFTER DELETE ON decisoes BEGIN
            INSERT INTO decisoes_fts(decisoes_fts, rowid, item_id, titulo, texto_completo)
            VALUES ('delete', old.rowid, old.item_id, old.titulo, old.texto_completo);
        END;
    """)

    cursor.execute("""
        CREATE TRIGGER IF NOT EXISTS decisoes_au AFTER UPDATE ON decisoes BEGIN
            INSERT INTO decisoes_fts(decisoes_fts, rowid, item_id, titulo, texto_completo)
            VALUES ('delete', old.rowid, old.item_id, old.titulo, old.texto_completo);
            INSERT INTO decisoes_fts(rowid, item_id, titulo, texto_completo)
            VALUES (new.rowid, new.item_id, new.titulo, new.texto_completo);
        END;
    """)

    cursor.execute("CREATE INDEX IF NOT EXISTS idx_decisoes_ano ON decisoes(ano_publicacao)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_decisoes_classificacao ON decisoes(classificacao_infracao)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_decisoes_multa ON decisoes(multa_principal_num)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_decisoes_origem_ais ON decisoes(origem_ais)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_decisoes_risco ON decisoes(risco)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_decisoes_porte ON decisoes(porte)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_decisoes_primariedade ON decisoes(primariedade)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_incisos_codigo ON decisao_incisos(inciso)")

    conn.commit()


def importar_csvs():
    if not OUTPUT_DIR.exists():
        print(f"Diretório {OUTPUT_DIR} não encontrado.")
        return

    arquivos_csv = sorted(OUTPUT_DIR.glob("anvisa_*/anvisa_*.csv"))
    if not arquivos_csv:
        print("Nenhum arquivo CSV individual encontrado para importação.")
        return

    conn = sqlite3.connect(DB_PATH)
    conn.execute("PRAGMA foreign_keys = ON;")
    inicializar_banco(conn)
    cursor = conn.cursor()

    total_importados = 0
    total_erros = 0

    print(f"Encontrados {len(arquivos_csv)} arquivos CSV. Iniciando importação para {DB_PATH.name}...")

    for caminho_csv in arquivos_csv:
        try:
            with open(caminho_csv, mode="r", encoding="utf-8-sig") as f:
                leitor = csv.DictReader(f, delimiter=";")
                linha = next(leitor, None)

            if not linha:
                continue

            item_id = caminho_csv.stem
            caminho_txt = caminho_csv.with_suffix(".txt")
            texto_completo = caminho_txt.read_text(encoding="utf-8") if caminho_txt.exists() else ""

            data_ass = linha.get("Data da Assinatura", "").strip()
            data_pub = linha.get("Data de Publicação (DSpace)", linha.get("Data de Publicação", "")).strip()
            valor_multa_raw = linha.get("Valor da multa aplicada", "").strip()
            classificacao = linha.get("Classificação da Infração", "").strip()
            incisos_raw = linha.get("Incisos do art. 10 imputados", "").strip()
            total_incisos = int(linha.get("Total_Incisos_Art10", 0) or 0)

            # Prioriza o ano da data de assinatura; se ausente, usa a data do DSpace
            ano_ref = extrair_ano(data_ass) or extrair_ano(data_pub)
            multa_num = parse_valor_monetario(valor_multa_raw)

            cursor.execute(
                """
                INSERT INTO decisoes (
                    item_id, arquivo_rastreio, titulo, data_assinatura, data_publicacao,
                    ano_publicacao, autor, url_pdf, origem_ais, risco, primariedade, porte,
                    valor_multa_raw, multa_principal_num, classificacao_infracao,
                    incisos_art_10_raw, total_incisos_art10, texto_completo, caminho_pasta
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(item_id) DO UPDATE SET
                    titulo = excluded.titulo,
                    data_assinatura = excluded.data_assinatura,
                    data_publicacao = excluded.data_publicacao,
                    ano_publicacao = excluded.ano_publicacao,
                    autor = excluded.autor,
                    url_pdf = excluded.url_pdf,
                    origem_ais = excluded.origem_ais,
                    risco = excluded.risco,
                    primariedade = excluded.primariedade,
                    porte = excluded.porte,
                    valor_multa_raw = excluded.valor_multa_raw,
                    multa_principal_num = excluded.multa_principal_num,
                    classificacao_infracao = excluded.classificacao_infracao,
                    incisos_art_10_raw = excluded.incisos_art_10_raw,
                    total_incisos_art10 = excluded.total_incisos_art10,
                    texto_completo = excluded.texto_completo
                """,
                (
                    item_id,
                    linha.get("Arquivo_Rastreio", f"{item_id}.pdf"),
                    linha.get("Título da Decisão", ""),
                    data_ass,
                    data_pub,
                    ano_ref,
                    linha.get("Autor", ""),
                    linha.get("URL do PDF", ""),
                    linha.get("Origem AIS", "Não encontrado").strip(),
                    linha.get("Risco", "Não encontrado").strip(),
                    linha.get("Primariedade", "Não encontrado").strip(),
                    linha.get("Porte", "Não encontrado").strip(),
                    valor_multa_raw,
                    multa_num,
                    classificacao,
                    incisos_raw,
                    total_incisos,
                    texto_completo,
                    str(caminho_csv.parent),
                ),
            )

            cursor.execute("DELETE FROM decisao_incisos WHERE item_id = ?", (item_id,))
            if incisos_raw and incisos_raw not in ("Não encontrado", "Não identificado"):
                lista_incisos = [inc.strip() for inc in incisos_raw.split(",") if inc.strip()]
                for inciso in lista_incisos:
                    cursor.execute(
                        "INSERT OR IGNORE INTO decisao_incisos (item_id, inciso) VALUES (?, ?)",
                        (item_id, inciso),
                    )

            total_importados += 1

        except Exception as e:
            total_erros += 1
            print(f"[ERRO] Falha ao importar {caminho_csv.name}: {e}")

    cursor.execute("INSERT INTO decisoes_fts(decisoes_fts) VALUES('optimize');")
    conn.commit()
    conn.close()

    print(f"\n=== Importação e Indexação FTS5 Concluídas! ===")
    print(f"Registros carregados/atualizados no SQLite: {total_importados}")
    if total_erros:
        print(f"Arquivos com erro de leitura: {total_erros}")
    print(f"Banco pronto em: {DB_PATH}")


if __name__ == "__main__":
    importar_csvs()