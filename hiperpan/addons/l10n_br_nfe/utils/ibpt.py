# Copyright (C) 2024
# License AGPL-3 - See http://www.gnu.org/licenses/agpl-3.0.html

import logging
import requests
from urllib.parse import quote

_logger = logging.getLogger(__name__)

IBPT_API_BASE_URL = "https://apidoni.ibpt.org.br/api/v1"


class IBPTError(Exception):
    """Custom exception for IBPT API errors"""

    pass


def get_ibpt_product_taxes(
    token,
    cnpj,
    ncm_code,
    uf,
    ex_tipi=0,
    description="",
    unit="UN",
    value=0.0,
    gtin="",
):
    """
    Fetch approximate tributes from IBPT API for a product.

    Args:
        token: IBPT API token
        cnpj: Company CNPJ (numbers only)
        ncm_code: NCM code (8 digits, numbers only)
        uf: Brazilian state code (2 letters)
        ex_tipi: Exception TIPI code (default 0)
        description: Product description
        unit: Unit of measure (default "UN")
        value: Product value
        gtin: Product GTIN/EAN code (optional)

    Returns:
        dict with tax rates:
            - nacional: Federal tax rate for national products (%)
            - estadual: State tax rate (%)
            - municipal: Municipal tax rate (%)
            - importado: Federal tax rate for imported products (%)

    Raises:
        IBPTError: If API request fails
    """
    if not token:
        raise IBPTError(
            "Token IBPT não configurado. Configure o token nas configurações da empresa."
        )

    if not cnpj:
        raise IBPTError("CNPJ da empresa não configurado.")

    if not ncm_code:
        raise IBPTError("Código NCM não informado.")

    if not uf:
        raise IBPTError("UF não informada.")

    # Clean the NCM code (remove dots and dashes)
    ncm_clean = "".join(filter(str.isdigit, str(ncm_code)))

    # Clean the CNPJ (remove dots, dashes, and slashes)
    cnpj_clean = "".join(filter(str.isdigit, str(cnpj)))

    # Endpoint for products
    url = f"{IBPT_API_BASE_URL}/produtos"

    # Parameters
    params = {
        "token": token,
        "cnpj": cnpj_clean,
        "codigo": ncm_clean,
        "uf": uf.upper(),
        "ex": ex_tipi or "0",
        "descricao": description or "",
        "unidadeMedida": unit or "UN",
        "valor": f"{value:.2f}",
        "gtin": gtin or "SEM GTIN",
    }

    _logger.info(f"Fetching IBPT data for NCM: {ncm_clean}, UF: {uf}, EX: {ex_tipi}")
    _logger.info(f"Params: {params}")

    try:
        response = requests.get(url, params=params, timeout=30)

        if response.status_code == 200:
            data = response.json()
            _logger.info(f"IBPT response: {data}")

            return {
                "nacional": data.get("Nacional", 0.0),
                "estadual": data.get("Estadual", 0.0),
                "municipal": data.get("Municipal", 0.0),
                "importado": data.get("Importado", 0.0),
                "fonte": data.get("Fonte", ""),
                "chave": data.get("Chave", ""),
                "versao": data.get("Versao", ""),
                "vigencia_inicio": data.get("VigenciaInicio", ""),
                "vigencia_fim": data.get("VigenciaFim", ""),
            }
        elif response.status_code == 401:

            raise IBPTError("Token IBPT inválido ou expirado.")
        elif response.status_code == 404:
            _logger.error(f"NCM {ncm_clean} não encontrado na base do IBPT.")
            raise IBPTError(f"NCM {ncm_clean} não encontrado na base do IBPT.")
        else:
            error_msg = f"Erro na API IBPT: {response.status_code}"
            try:
                error_data = response.json()
                if "Message" in error_data:
                    error_msg = f"Erro IBPT: {error_data['Message']}"
            except:
                pass
            _logger.error(f"IBPT error: {error_msg}")
            raise IBPTError(error_msg)

    except requests.exceptions.Timeout:
        raise IBPTError("Timeout ao conectar com a API IBPT. Tente novamente.")
    except requests.exceptions.ConnectionError:
        raise IBPTError(
            "Erro de conexão com a API IBPT. Verifique sua conexão com a internet."
        )
    except requests.exceptions.RequestException as e:
        raise IBPTError(f"Erro ao conectar com a API IBPT: {str(e)}")


# TODO: esse metodo não foi revisado. Deve ser revisado antes de qualquer uso.
def get_ibpt_service_taxes(
    token, cnpj, nbs_code, uf, description="", unit="UN", value=0.0
):
    """
    Fetch approximate tributes from IBPT API for a service.

    Args:
        token: IBPT API token
        cnpj: Company CNPJ (numbers only)
        nbs_code: NBS code for services
        uf: Brazilian state code (2 letters)
        description: Service description
        unit: Unit of measure (default "UN")
        value: Service value

    Returns:
        dict with tax rates similar to product taxes

    Raises:
        IBPTError: If API request fails
    """
    if not token:
        raise IBPTError(
            "Token IBPT não configurado. Configure o token nas configurações da empresa."
        )

    if not cnpj:
        raise IBPTError("CNPJ da empresa não configurado.")

    if not nbs_code:
        raise IBPTError("Código NBS não informado.")

    if not uf:
        raise IBPTError("UF não informada.")

    # Clean the NBS code
    nbs_clean = "".join(filter(str.isdigit, str(nbs_code)))

    # Clean the CNPJ
    cnpj_clean = "".join(filter(str.isdigit, str(cnpj)))

    # Endpoint for services
    url = f"{IBPT_API_BASE_URL}/servicos"

    params = {
        "token": token,
        "cnpj": cnpj_clean,
        "codigo": nbs_clean,
        "uf": uf.upper(),
        "descricao": description or "",
        "unidadeMedida": unit or "UN",
        "valor": f"{value:.2f}",
    }

    _logger.info(f"Fetching IBPT service data for NBS: {nbs_clean}, UF: {uf}")

    try:
        response = requests.get(url, params=params, timeout=30)

        if response.status_code == 200:
            data = response.json()
            _logger.info(f"IBPT service response: {data}")

            return {
                "nacional": data.get("Nacional", 0.0),
                "estadual": data.get("Estadual", 0.0),
                "municipal": data.get("Municipal", 0.0),
                "importado": data.get("Importado", 0.0),
                "fonte": data.get("Fonte", ""),
                "chave": data.get("Chave", ""),
                "versao": data.get("Versao", ""),
                "vigencia_inicio": data.get("VigenciaInicio", ""),
                "vigencia_fim": data.get("VigenciaFim", ""),
            }
        elif response.status_code == 401:
            raise IBPTError("Token IBPT inválido ou expirado.")
        elif response.status_code == 404:
            raise IBPTError(f"NBS {nbs_clean} não encontrado na base do IBPT.")
        else:
            error_msg = f"Erro na API IBPT: {response.status_code}"
            try:
                error_data = response.json()
                if "Message" in error_data:
                    error_msg = f"Erro IBPT: {error_data['Message']}"
            except:
                pass
            raise IBPTError(error_msg)

    except requests.exceptions.Timeout:
        raise IBPTError("Timeout ao conectar com a API IBPT. Tente novamente.")
    except requests.exceptions.ConnectionError:
        raise IBPTError(
            "Erro de conexão com a API IBPT. Verifique sua conexão com a internet."
        )
    except requests.exceptions.RequestException as e:
        raise IBPTError(f"Erro ao conectar com a API IBPT: {str(e)}")


def calculate_approximate_taxes(
    tax_rates, value_with_discount, quantity, is_imported=False
):
    """
    Calculate the approximate tax amounts based on IBPT rates.

    Args:
        tax_rates: Dict with tax rates from IBPT API
        total_value: Total value of the product/service
        is_imported: Whether the product is imported (to use "importado" rate)

    Returns:
        dict with calculated tax amounts:
            - federal: Federal tax amount
            - estadual: State tax amount
            - municipal: Municipal tax amount
            - total: Total approximate tax amount
    """
    federal_rate = tax_rates.get("importado" if is_imported else "nacional", 0.0)
    state_rate = tax_rates.get("estadual", 0.0)
    municipal_rate = tax_rates.get("municipal", 0.0)

    total_value = value_with_discount * quantity
    federal_amount = round(total_value * (federal_rate / 100), 2)
    state_amount = round(total_value * (state_rate / 100), 2)
    municipal_amount = round(total_value * (municipal_rate / 100), 2)

    return {
        "federal": federal_amount,
        "estadual": state_amount,
        "municipal": municipal_amount,
        "total": federal_amount + state_amount + municipal_amount,
        "federal_rate": federal_rate,
        "state_rate": state_rate,
        "municipal_rate": municipal_rate,
    }
