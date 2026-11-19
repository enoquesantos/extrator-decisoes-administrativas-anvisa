import argparse
import csv
import time
from pathlib import Path

from config import OUTPUT_DIR, SLEEP_TIME, START_URL, registrar_falha
from extractor import (INCISOS_ART10_LISTA, converter_pdf_para_txt,
                       extrair_dados_decisao)
from scraper import (baixar_pdf, criar_sessao, extrair_itens_listagem,
                     obter_url_pdf_e_metadados)

COLUNAS_INCISOS = [f"Art10_{inc}" for inc in INCISOS_ART10_LISTA]

COLUNAS_CSV = [
    "Arquivo_Rastreio",
    "Título da Decisão",
    "Data da Assinatura",
    "Data de Publicação (DSpace)",
    "Autor",
    "URL do PDF",
    "Origem AIS",
    "Risco",
    "Primariedade",
    "Porte",
    "Valor da multa aplicada",
    "Classificação da Infração",
    "Incisos do art. 10 imputados",
    "Total_Incisos_Art10",
] + COLUNAS_INCISOS


def salvar_csv(caminho_csv: Path, dados_linha: dict, modo: str = "w"):
    """Salva ou adiciona uma linha em um arquivo CSV com codificação UTF-8-SIG (compatível com Excel/Pandas)."""
    arquivo_existe = caminho_csv.exists()
    with open(caminho_csv, mode=modo, newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=COLUNAS_CSV, delimiter=";")
        if modo == "w" or not arquivo_existe:
            writer.writeheader()
        writer.writerow(dados_linha)


def processar_item(session, item: dict, csv_consolidado: Path) -> bool:
    item_id = item["item_id"]
    pasta_item = OUTPUT_DIR / item_id
    pasta_item.mkdir(parents=True, exist_ok=True)

    caminho_pdf = pasta_item / f"{item_id}.pdf"
    caminho_txt = pasta_item / f"{item_id}.txt"
    caminho_csv = pasta_item / f"{item_id}.csv"

    if caminho_csv.exists() and caminho_pdf.exists() and caminho_pdf.stat().st_size > 100:
        print(f"[PULANDO] {item_id} já foi processado anteriormente.")
        return False

    print(f"[PROCESSANDO] {item_id} - {item['titulo'][:60]}...")

    try:
        item = obter_url_pdf_e_metadados(session, item)
    except Exception as e:
        registrar_falha(item_id, item["url_detalhes"], f"Erro ao acessar página secundária de detalhes: {str(e)}")
        return False

    url_pdf = item.get("url_pdf")
    if not url_pdf:
        registrar_falha(item_id, item["url_detalhes"], "Link do PDF não encontrado na tabela 'Arquivos associados'.")
        return False

    if not baixar_pdf(session, url_pdf, caminho_pdf, item_id):
        return False

    texto = converter_pdf_para_txt(caminho_pdf, caminho_txt, item_id, url_pdf)
    if texto is None:
        return False

    dados_extraidos = extrair_dados_decisao(texto)

    linha_csv = {
        "Arquivo_Rastreio": f"{item_id}.pdf",
        "Título da Decisão": item.get("titulo", ""),
        "Data da Assinatura": dados_extraidos["data_assinatura"],
        "Data de Publicação (DSpace)": item.get("data_publicacao", ""),
        "Autor": item.get("autor", ""),
        "URL do PDF": url_pdf,
        "Origem AIS": dados_extraidos["origem_ais"],
        "Risco": dados_extraidos["risco"],
        "Primariedade": dados_extraidos["primariedade"],
        "Porte": dados_extraidos["porte"],
        "Valor da multa aplicada": dados_extraidos["valor_multa"],
        "Classificação da Infração": dados_extraidos["classificacao_infracao"],
        "Incisos do art. 10 imputados": dados_extraidos["incisos_art_10"],
        "Total_Incisos_Art10": dados_extraidos["total_incisos_art_10"],
    }

    # Adiciona as 42 colunas binárias (0 ou 1) dos incisos
    for col in COLUNAS_INCISOS:
        linha_csv[col] = dados_extraidos[col]

    salvar_csv(caminho_csv, linha_csv, modo="w")
    salvar_csv(csv_consolidado, linha_csv, modo="a")
    print(
        f"[OK] {item_id} | Data: {dados_extraidos['data_assinatura']} | "
        f"AIS: {dados_extraidos['origem_ais']} | Risco: {dados_extraidos['risco']} | "
        f"Porte: {dados_extraidos['porte']} | Prim.: {dados_extraidos['primariedade']}"
    )
    return True


def executar_pipeline(limite: int | None = None):
    session = criar_sessao()
    url_atual = START_URL
    csv_consolidado = OUTPUT_DIR / "dataset_consolidado.csv"
    pagina = 1
    total_verificados = 0
    novos_processados = 0

    modo_str = f"MODO TESTE (Limite: {limite} novos itens)" if limite else "COLETA COMPLETA"
    print(f"=== Iniciando Extração ANVISA [{modo_str}] ===")

    while url_atual:
        print(f"\n---> Navegando na Página de Listagem {pagina}: {url_atual}")
        try:
            itens_pagina, proxima_url = extrair_itens_listagem(session, url_atual)
        except Exception as e:
            registrar_falha(f"PAGINA_{pagina}", url_atual, f"Erro crítico ao carregar listagem: {str(e)}")
            break

        if not itens_pagina:
            print("Nenhum item encontrado nesta página. Encerrando paginação.")
            break

        for item in itens_pagina:
            foi_processado = processar_item(session, item, csv_consolidado)
            total_verificados += 1

            if foi_processado:
                novos_processados += 1

            if limite and novos_processados >= limite:
                print(f"\n[LIMITE ATINGIDO] {novos_processados} novos itens processados com sucesso.")
                print(f"Confira os arquivos gerados em: {OUTPUT_DIR}")
                return

            time.sleep(SLEEP_TIME)

        url_atual = proxima_url
        pagina += 1

    print(f"\n=== Processamento Concluído! Verificados: {total_verificados} | Novos: {novos_processados} ===")
    print(f"Arquivos salvos em: {OUTPUT_DIR}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Scraper e extrator de decisões da ANVISA.")
    parser.add_argument(
        "-l",
        "--limite",
        type=int,
        default=None,
        help="Define o número máximo de novos itens a baixar/processar (ex: --limite 5).",
    )
    args = parser.parse_args()
    executar_pipeline(limite=args.limite)