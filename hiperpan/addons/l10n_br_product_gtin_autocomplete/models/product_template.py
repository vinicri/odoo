"""
Brazilian Product GTIN Autocomplete
"""

import base64
import logging
import re
from lxml import etree
import requests
from cryptography.hazmat.primitives.serialization import (
    Encoding,
    PrivateFormat,
    NoEncryption,
    pkcs12,
)
from odoo import api, fields, models, _
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)


class ProductTemplate(models.Model):
    _inherit = "product.template"

    search_gtin = fields.Char(
        string="Buscar por GTIN/EAN",
        help="Digite o código GTIN/EAN para consulta automática no CCG (Cadastro Centralizado de GTIN)",
    )

    @api.onchange("search_gtin")
    def _onchange_search_gtin(self):
        """
        Quando o GTIN for digitado, consulta automaticamente no CCG
        """
        if self.id or not self.search_gtin:
            return

        # Remove caracteres não numéricos
        clean_gtin = re.sub(r"\D", "", self.search_gtin)

        # Verifica se o tamanho é válido (8, 12, 13 ou 14 dígitos)
        if len(clean_gtin) not in [8, 12, 13, 14]:
            return

        # Realiza a consulta no CCG
        try:
            product_data = self._consult_ccg_gtin(clean_gtin)
            _logger.info(f"Dados obtidos do CCG: {product_data}")
            if product_data:
                # Atualiza os campos do produto
                self.update(product_data)
        except UserError as e:
            return {"warning": {"title": _("Erro na consulta"), "message": str(e)}}
        except Exception as e:
            _logger.error(f"Erro inesperado na consulta CCG: {str(e)}", exc_info=True)
            return {
                "warning": {
                    "title": _("Erro na consulta"),
                    "message": _(
                        "Erro inesperado ao consultar CCG. Verifique os logs para mais detalhes."
                    ),
                }
            }

    def _get_company_certificate(self):
        """
        Obtém o certificado digital da empresa para autenticação no CCG
        """
        company = self.env.company

        # Busca certificado A1 válido
        certificate = company.get_nfe_certificate_pkcs12()

        return certificate

    def _validate_gtin_checkdigit(self, gtin):
        """
        Valida o dígito verificador do GTIN

        Args:
            gtin: GTIN com 8, 12, 13 ou 14 dígitos

        Returns:
            True se válido, False caso contrário
        """
        # Normaliza para 14 dígitos
        gtin_normalized = gtin.zfill(14)

        # Calcula dígito verificador
        odd_sum = sum(int(gtin_normalized[i]) for i in range(0, 13, 2))
        even_sum = sum(int(gtin_normalized[i]) for i in range(1, 13, 2))
        total = (odd_sum * 3) + even_sum
        check_digit = (10 - (total % 10)) % 10

        return check_digit == int(gtin_normalized[13])

    def _validate_gtin_prefix(self, gtin):
        """
        Valida se o GTIN possui prefixo GS1 Brasil (789 ou 790)

        Args:
            gtin: GTIN com 8, 12, 13 ou 14 dígitos

        Returns:
            True se possui prefixo Brasil, False caso contrário
        """
        # Normaliza para 14 dígitos
        gtin_normalized = gtin.zfill(14)

        # Identifica prefixo GS1
        if gtin_normalized[:6] == "000000":
            # GTIN-8: prefixo nas posições 6-8 (índices 6,7,8)
            prefix = gtin_normalized[6:9]
        else:
            # GTIN-12, 13, 14: prefixo nas posições 2-4 (índices 1,2,3)
            prefix = gtin_normalized[1:4]

        return prefix in ["789", "790"]

    def _build_consgtin_xml(self, gtin):
        """
        Constrói o XML de consulta GTIN (consGTIN)

        Args:
            gtin: Código GTIN (8, 12, 13 ou 14 dígitos)

        Returns:
            String com XML de consulta
        """
        ns = "http://www.portalfiscal.inf.br/nfe"
        root = etree.Element("{%s}consGTIN" % ns, versao="9.99", nsmap={None: ns})

        # GTIN
        gtin_elem = etree.SubElement(root, "GTIN")
        gtin_elem.text = gtin

        # Não incluir declaração XML pois vai dentro do SOAP
        xml_string = etree.tostring(
            root, encoding="unicode", pretty_print=False, xml_declaration=False
        )

        return xml_string

    def _send_soap_request(self, url, xml_content, certificado):
        """
        Envia requisição SOAP para CCG com autenticação por certificado digital

        Args:
            url: URL do webservice
            xml_content: Conteúdo XML da requisição
            certificado: Dict com cert_file e password

        Returns:
            Response da requisição
        """
        # Preparar certificado usando cryptography
        try:
            cert_bytes = base64.b64decode(certificado["cert_file"])
            private_key, certificate, additional_certs = (
                pkcs12.load_key_and_certificates(
                    cert_bytes, certificado["password"].encode("utf-8")
                )
            )

            # Serializar chave privada e certificado para PEM
            key_pem = private_key.private_bytes(
                encoding=Encoding.PEM,
                format=PrivateFormat.TraditionalOpenSSL,
                encryption_algorithm=NoEncryption(),
            )

            cert_pem = certificate.public_bytes(Encoding.PEM)

        except Exception as e:
            _logger.error(f"Erro ao processar certificado: {str(e)}")
            raise UserError(_("Erro ao processar certificado digital: %s") % str(e))

        # Criar arquivos temporários para certificado e chave
        import tempfile

        with tempfile.NamedTemporaryFile(
            mode="wb", delete=False, suffix=".pem"
        ) as cert_file:
            cert_file.write(cert_pem)
            cert_path = cert_file.name

        with tempfile.NamedTemporaryFile(
            mode="wb", delete=False, suffix=".key"
        ) as key_file:
            key_file.write(key_pem)
            key_path = key_file.name

        try:
            # Envelope SOAP 1.2 para ccgConsGTIN
            soap_env = f"""<?xml version="1.0" encoding="utf-8"?>
<soap:Envelope xmlns:soap="http://www.w3.org/2003/05/soap-envelope"
               xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
               xmlns:xsd="http://www.w3.org/2001/XMLSchema">
    <soap:Body>
        <nfeDadosMsg xmlns="http://www.portalfiscal.inf.br/nfe/wsdl/CadConsultaCadastro4">
            {xml_content}
        </nfeDadosMsg>
    </soap:Body>
</soap:Envelope>"""

            headers = {
                "Content-Type": "application/soap+xml; charset=utf-8",
            }

            _logger.info(f"Enviando consulta GTIN para {url}")
            _logger.debug(f"SOAP Envelope:\n{soap_env}")

            response = requests.post(
                url,
                data=soap_env.encode("utf-8"),
                headers=headers,
                cert=(cert_path, key_path),
                timeout=30,
            )

            _logger.info(f"Resposta recebida - Status: {response.status_code}")

            if response.status_code != 200:
                _logger.error(f"Erro HTTP: {response.status_code} - {response.text}")
                raise UserError(
                    _("Erro ao consultar CCG: HTTP %s") % response.status_code
                )

            return response

        finally:
            # Limpar arquivos temporários
            import os

            try:
                os.unlink(cert_path)
                os.unlink(key_path)
            except Exception as e:
                _logger.warning(f"Erro ao remover arquivos temporários: {str(e)}")

    def _parse_ccg_response(self, response_xml):
        """
        Faz o parse da resposta XML da consulta GTIN

        Args:
            response_xml: XML de resposta do CCG

        Returns:
            Dict com dados do produto
        """
        try:
            # Parse do XML
            root = etree.fromstring(response_xml.encode("utf-8"))

            # Namespaces
            namespaces = {
                "soap": "http://www.w3.org/2003/05/soap-envelope",
                "nfe": "http://www.portalfiscal.inf.br/nfe",
            }

            # Extrair retConsGTIN do SOAP body
            ret_cons_gtin = root.xpath("//nfe:retConsGTIN", namespaces=namespaces)

            # Fallback genérico
            if not ret_cons_gtin:
                ret_cons_gtin = root.xpath("//*[local-name()='retConsGTIN']")

            if not ret_cons_gtin:
                _logger.error("Elemento retConsGTIN não encontrado na resposta")
                raise UserError(_("Resposta inválida do CCG"))

            ret_cons_gtin = ret_cons_gtin[0]

            # Verificar código de status
            c_stat = ret_cons_gtin.find("nfe:cStat", namespaces)
            x_motivo = ret_cons_gtin.find("nfe:xMotivo", namespaces)

            if c_stat is None:
                raise UserError(_("Resposta sem código de status"))

            status_code = c_stat.text
            status_msg = x_motivo.text if x_motivo is not None else "Erro desconhecido"

            # Código 9490 = Sucesso
            if status_code != "9490":
                _logger.error(f"Erro CCG: {status_code} - {status_msg}")
                raise UserError(
                    _("CCG retornou erro: %s - %s") % (status_code, status_msg)
                )

            # Extrair dados do produto
            product_data = {}

            # GTIN
            gtin = ret_cons_gtin.find("nfe:GTIN", namespaces)
            if gtin is not None and gtin.text:
                product_data["barcode"] = gtin.text

            # Descrição do Produto
            x_prod = ret_cons_gtin.find("nfe:xProd", namespaces)
            if x_prod is not None and x_prod.text:
                product_data["name"] = x_prod.text

            # NCM
            ncm = ret_cons_gtin.find("nfe:NCM", namespaces)
            if ncm is not None and ncm.text:
                # Buscar fiscal_classification_id pelo código NCM
                ncm_obj = self.env["l10n_br_fiscal.ncm"].search(
                    [("code", "=", ncm.text)], limit=1
                )
                if ncm_obj:
                    product_data["fiscal_classification_id"] = ncm_obj.id
                else:
                    _logger.warning(f"NCM {ncm.text} não encontrado no sistema")

            # CEST - pode haver múltiplos
            cest_elements = ret_cons_gtin.findall("nfe:CEST", namespaces)
            if cest_elements:
                # Pega o primeiro CEST se houver múltiplos
                cest_code = cest_elements[0].text
                if cest_code:
                    # Buscar CEST no sistema
                    cest_obj = self.env["l10n_br_fiscal.cest"].search(
                        [("code", "=", cest_code)], limit=1
                    )
                    if cest_obj:
                        product_data["cest_id"] = cest_obj.id
                    else:
                        _logger.warning(f"CEST {cest_code} não encontrado no sistema")

            _logger.info(f"Dados extraídos da consulta GTIN: {product_data}")
            return product_data

        except etree.XMLSyntaxError as e:
            _logger.error(f"Erro de sintaxe XML na resposta: {str(e)}")
            raise UserError(_("Erro ao processar resposta do CCG: XML inválido"))
        except Exception as e:
            _logger.error(f"Erro ao fazer parse da resposta: {str(e)}", exc_info=True)
            raise

    def _consult_ccg_gtin(self, gtin):
        """
        Consulta o GTIN no Cadastro Centralizado de GTIN (CCG)

        Args:
            gtin: Código GTIN (8, 12, 13 ou 14 dígitos)

        Returns:
            Dict com dados do produto ou None se não encontrado
        """
        # Validar dígito verificador
        if not self._validate_gtin_checkdigit(gtin):
            raise UserError(_("GTIN com dígito verificador inválido: %s") % gtin)

        # Validar prefixo Brasil (789 ou 790)
        if not self._validate_gtin_prefix(gtin):
            raise UserError(
                _(
                    "GTIN não possui prefixo GS1 Brasil (789 ou 790).\n"
                    "Este serviço só consulta produtos registrados na GS1 Brasil."
                )
            )

        # Obter certificado
        certificate = self._get_company_certificate()

        # URL do webservice CCG (SVRS - Produção)
        url = "https://dfe-servico.svrs.rs.gov.br/ws/ccgConsGTIN/ccgConsGTIN.asmx"

        # Construir XML de consulta
        xml_content = self._build_consgtin_xml(gtin)

        _logger.info(f"Consultando GTIN {gtin} no CCG")
        _logger.debug(f"XML de consulta:\n{xml_content}")

        # Enviar requisição SOAP
        response = self._send_soap_request(url, xml_content, certificate)

        _logger.info(f"Resposta CCG:\n{response.text}")

        # Parse da resposta
        product_data = self._parse_ccg_response(response.text)

        return product_data
