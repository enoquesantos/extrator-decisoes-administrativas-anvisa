'''
Implementa a navegação exata na árvore DOM solicitada para a listagem e para a página de detalhes, além de lidar com a paginação do DSpace (offset) até cobrir todas as decisões.
'''

from pathlib import Path
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from config import BASE_URL, HEADERS, REQUEST_TIMEOUT, registrar_falha


def criar_sessao() -> requests.Session:
    """Cria uma sessão HTTP resiliente com Retry automático para quedas momentâneas."""
    session = requests.Session()
    session.headers.update(HEADERS)
    retry = Retry(
        total=3,
        backoff_factor=2,
        status_forcelist=[429, 500, 502, 503, 504],
        allowed_methods=["GET"],
    )
    adapter = HTTPAdapter(max_retries=retry)
    session.mount("http://", adapter)
    session.mount("https://", adapter)
    return session


def extrair_itens_listagem(session: requests.Session, url_listagem: str) -> tuple[list[dict], str | None]:
    """
    Acessa a página de listagem do DSpace, extrai os metadados básicos da linha
    (Data, Título, Link secundário, Autor) e descobre o link da próxima página.
    """
    resp = session.get(url_listagem, timeout=REQUEST_TIMEOUT)
    resp.raise_for_status()
    soup = BeautifulSoup(resp.text, "lxml")

    # Localiza a tabela principal pelo summary específico do DSpace ou classe .table
    tabela = soup.find(
        "table",
        attrs={"summary": "Esta tabela navega por todo conteúdo dspace BrowseListTag"},
    )
    if not tabela:
        tabela = soup.select_one("table.table")

    itens = []
    if not tabela:
        return itens, None

    # Busca todas as linhas dentro de tbody (ou diretamente na table caso o navegador/parser omita tbody)
    linhas = tabela.select("tbody > tr") or tabela.find_all("tr")

    for tr in linhas:
        td_titulo = tr.find("td", attrs={"headers": "t2"})
        if not td_titulo:
            continue

        # Caminho exato: td[headers="t2"] > strong > a (com fallback caso algum item não tenha <strong>)
        tag_a = td_titulo.select_one("strong > a") or td_titulo.find("a")
        if not tag_a or not tag_a.get("href"):
            continue

        link_detalhes = urljoin(BASE_URL, tag_a["href"].strip())
        titulo = tag_a.get_text(strip=True)

        # Extrai ID único do handle (ex: /jspui/handle/anvisa/22566 -> anvisa_22566)
        partes_url = [p for p in link_detalhes.split("/") if p]
        codigo_id = partes_url[-1] if partes_url else "desconhecido"
        item_id = f"anvisa_{codigo_id}"

        # No DSpace BrowseListTag: t1 = Data de Publicação, t3 = Autor(es)
        td_data = tr.find("td", attrs={"headers": "t1"})
        td_autor = tr.find("td", attrs={"headers": "t3"})

        data_pub = td_data.get_text(strip=True) if td_data else ""
        autor = td_autor.get_text(strip=True) if td_autor else ""

        itens.append({
            "item_id": item_id,
            "titulo": titulo,
            "data_publicacao": data_pub,
            "autor": autor,
            "url_detalhes": link_detalhes,
        })

    # Paginação do DSpace: procura botão/link de "Próxima" página
    proxima_url = None
    link_prox = (
        soup.select_one("ul.pagination li a.next-page-link")
        or soup.find("a", string=lambda s: s and ("Próxima" in s or "Next" in s or "Seguinte" in s))
    )
    if link_prox and link_prox.get("href"):
        proxima_url = urljoin(BASE_URL, link_prox["href"])

    return itens, proxima_url


def obter_url_pdf_e_metadados(session: requests.Session, item: dict) -> dict:
    """
    Acessa a página secundária (detalhes), refina metadados (caso ausentes na tabela inicial)
    e localiza o link do PDF no painel 'Arquivos associados a este item:'.
    """
    url_detalhes = item["url_detalhes"]
    resp = session.get(url_detalhes, timeout=REQUEST_TIMEOUT)
    resp.raise_for_status()
    soup = BeautifulSoup(resp.text, "lxml")

    # Fallback via meta tags Dublin Core caso data ou autor não estejam preenchidos na listagem
    if not item.get("data_publicacao"):
        meta_date = soup.find("meta", attrs={"name": "DC.date.issued"})
        if meta_date and meta_date.get("content"):
            item["data_publicacao"] = meta_date["content"].strip()

    if not item.get("autor"):
        meta_author = soup.find("meta", attrs={"name": "DC.creator"}) or soup.find(
            "meta", attrs={"name": "DC.contributor"}
        )
        if meta_author and meta_author.get("content"):
            item["autor"] = meta_author["content"].strip()

    # Localiza div.panel-heading contendo "Arquivos associados a este item:"
    painel_arquivos = None
    for div in soup.select("div.panel-heading"):
        if "Arquivos associados a este item:" in div.get_text():
            painel_arquivos = div.parent
            break

    url_pdf = None
    if painel_arquivos:
        # Caminho: table.table.panel-body > tbody > tr[1] > td.standard.break-all > a
        tabela_pdf = painel_arquivos.select_one("table.table.panel-body")
        if tabela_pdf:
            link_tag = tabela_pdf.select_one("tbody > tr > td.standard.break-all > a") or tabela_pdf.select_one(
                "tr > td.standard.break-all > a"
            )
            if link_tag and link_tag.get("href"):
                url_pdf = urljoin(BASE_URL, link_tag["href"].strip())

    # Fallback de segurança caso algum item antigo no DSpace tenha classe ligeiramente diferente
    if not url_pdf:
        link_fallback = soup.select_one('a[href*="/bitstream/"]')
        if link_fallback and link_fallback.get("href"):
            url_pdf = urljoin(BASE_URL, link_fallback["href"].strip())

    item["url_pdf"] = url_pdf
    return item


def baixar_pdf(session: requests.Session, url_pdf: str, destino_pdf: Path, item_id: str) -> bool:
    """
    Baixa o arquivo PDF via stream e verifica a assinatura mágica (%PDF)
    para garantir que não baixou uma página de erro HTML no lugar do documento.
    """
    try:
        with session.get(url_pdf, stream=True, timeout=REQUEST_TIMEOUT) as r:
            r.raise_for_status()
            with open(destino_pdf, "wb") as f:
                for chunk in r.iter_content(chunk_size=8192):
                    if chunk:
                        f.write(chunk)

        # Verifica integridade básica do arquivo (tamanho > 0 e cabeçalho %PDF)
        if not destino_pdf.exists() or destino_pdf.stat().st_size < 100:
            registrar_falha(item_id, url_pdf, "Arquivo PDF vazio ou incompleto após download.")
            return False

        with open(destino_pdf, "rb") as f:
            cabecalho = f.read(5)
            if not cabecalho.startswith(b"%PDF"):
                registrar_falha(item_id, url_pdf, "Arquivo baixado não possui cabeçalho válido %PDF (corrompido).")
                return False

        return True

    except Exception as e:
        registrar_falha(item_id, url_pdf, f"Falha no download do PDF: {str(e)}")
        return False