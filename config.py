'''
Centraliza os diretórios, cabeçalhos HTTP, tempo de pausa (3s) e configura o logger para registrar imediatamente no disco qualquer arquivo corrompido ou falha de rede.
'''

import logging
from pathlib import Path

# Diretórios base
BASE_DIR = Path(__file__).resolve().parent
OUTPUT_DIR = BASE_DIR / "dados_extraidos"
LOG_DIR = BASE_DIR / "logs"

OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
LOG_DIR.mkdir(parents=True, exist_ok=True)

# URLs e Parâmetros
BASE_URL = "https://bibliotecadigital.anvisa.gov.br"
START_URL = f"{BASE_URL}/jspui/handle/anvisa/12265"
SLEEP_TIME = 3  # Pausa obrigatória de 3 segundos por item
REQUEST_TIMEOUT = 30

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/128.0.0.0 Safari/537.36"
    ),
    "AcceptLanguage": "pt-BR,pt;q=0.9,en-US;q=0.8,en;q=0.7",
}

# Configuração do Log de Falhas (salva em arquivo a cada erro)
LOG_FILE = LOG_DIR / "falhas.log"

failure_logger = logging.getLogger("anvisa_failures")
failure_logger.setLevel(logging.ERROR)

file_handler = logging.FileHandler(LOG_FILE, mode="a", encoding="utf-8")
formatter = logging.Formatter(
    fmt="%(asctime)s | [%(levelname)s] | ID: %(item_id)s | URL: %(url)s | Erro: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
file_handler.setFormatter(formatter)
failure_logger.addHandler(file_handler)


def registrar_falha(item_id: str, url: str, mensagem: str):
    """Grava imediatamente no arquivo de log qualquer falha de download ou PDF corrompido."""
    failure_logger.error(mensagem, extra={"item_id": item_id, "url": url})
    for handler in failure_logger.handlers:
        handler.flush()
