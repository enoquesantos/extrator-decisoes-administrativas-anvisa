import sqlite3
from pathlib import Path

from config import BASE_DIR

DB_PATH = BASE_DIR / "anvisa_decisoes.db"

VALORES_AUSENTES = (
    "",
    "não encontrado",
    "não identificado",
    "sem multa pecuniária / não encontrado",
)


def eh_valido(valor) -> bool:
    """Retorna True se o campo foi efetivamente preenchido pela extração."""
    if valor is None:
        return False
    if isinstance(valor, (int, float)):
        return valor > 0
    return str(valor).strip().lower() not in VALORES_AUSENTES


def executar_auditoria():
    if not DB_PATH.exists():
        print(f"Erro: Banco de dados não encontrado em {DB_PATH}.")
        print("Execute 'python importar_sqlite.py' antes de rodar a auditoria.")
        return

    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    cursor.execute("""
        SELECT
            item_id,
            data_assinatura,
            origem_ais,
            risco,
            primariedade,
            porte,
            multa_principal_num,
            classificacao_infracao,
            total_incisos_art10,
            LENGTH(TRIM(COALESCE(texto_completo, ''))) AS tamanho_texto
        FROM decisoes
    """)
    registros = cursor.fetchall()
    conn.close()

    total = len(registros)
    if total == 0:
        print("O banco de dados está vazio. Nenhum registro para auditar.")
        return

    sem_texto = [r["item_id"] for r in registros if r["tamanho_texto"] == 0]
    com_texto = [r for r in registros if r["tamanho_texto"] > 0]
    total_com_texto = len(com_texto)

    # Mapeamento: (Rótulo exibido, nome da coluna no SQLite)
    campos = [
        ("Data da Assinatura", "data_assinatura"),
        ("Origem AIS", "origem_ais"),
        ("Risco", "risco"),
        ("Primariedade", "primariedade"),
        ("Porte", "porte"),
        ("Valor da Multa (R$)", "multa_principal_num"),
        ("Classificação da Infração", "classificacao_infracao"),
        ("Incisos do Art. 10", "total_incisos_art10"),
    ]

    print("=" * 94)
    print(f" AUDITORIA DE QUALIDADE DA EXTRAÇÃO - {DB_PATH.name}")
    print("=" * 94)
    print(f" Total de decisões no banco      : {total}")
    print(f" PDFs com texto extraível        : {total_com_texto} ({(total_com_texto / total) * 100:.1f}%)")
    print(f" PDFs sem texto (provável scan)  : {len(sem_texto)} ({(len(sem_texto) / total) * 100:.1f}%)")
    print("=" * 94)

    cabecalho = (
        f"{'Campo':<27} | {'Encontrado':>17} | {'Não Encontrado':>17} | {'Acerto (c/ texto)':>18}"
    )
    print(cabecalho)
    print("-" * 94)

    amostras_falhas: dict[str, list[str]] = {}

    for rotulo, coluna in campos:
        encontrados = sum(1 for r in registros if eh_valido(r[coluna]))
        nao_encontrados = total - encontrados
        pct_enc = (encontrados / total) * 100
        pct_nao = (nao_encontrados / total) * 100

        # Taxa de acerto desconsiderando PDFs que são imagem pura (sem texto)
        if total_com_texto > 0:
            enc_com_texto = sum(1 for r in com_texto if eh_valido(r[coluna]))
            pct_real = f"{(enc_com_texto / total_com_texto) * 100:6.1f}%"
        else:
            pct_real = "   N/A "

        print(
            f"{rotulo:<27} | {encontrados:>7} ({pct_enc:5.1f}%) | "
            f"{nao_encontrados:>7} ({pct_nao:5.1f}%) | {pct_real:>18}"
        )

        # Guarda até 5 IDs de exemplo onde havia texto mas o campo não foi encontrado
        falhas_campo = [r["item_id"] for r in com_texto if not eh_valido(r[coluna])][:5]
        if falhas_campo:
            amostras_falhas[rotulo] = falhas_campo

    print("=" * 94)

    # Exibe amostras de IDs para facilitar a calibração das regex no extractor.py
    if amostras_falhas:
        print("\nAmostra de IDs COM texto onde o campo NÃO foi encontrado (até 5 por campo):")
        for rotulo, ids in amostras_falhas.items():
            print(f"  - {rotulo:<25}: {', '.join(ids)}")

    if sem_texto:
        print(f"\nPrimeiros IDs sem camada de texto (candidatos a OCR): {', '.join(sem_texto[:10])}")


if __name__ == "__main__":
    executar_auditoria()