"""
Brazilian Partner NFe Autocomplete
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
from odoo.exceptions import UserError, ValidationError
from erpbrasil.base.fiscal import cnpj_cpf as cnpj_cpf_module

from odoo.addons.l10n_br_fiscal.utils.endpoints import get_nfe_endpoint_by_state  # type: ignore[import-untyped]

_logger = logging.getLogger(__name__)


class ResPartner(models.Model):
    _inherit = "res.partner"

    search_cnpj_cpf = fields.Char(string="CNPJ/CPF para procurar", size=14)

    @api.onchange("search_cnpj_cpf")
    def _onchange_search_cnpj_cpf(self):
        """
        Quando o CNPJ/CPF estiver completo, consulta automaticamente na SEFAZ
        """
        if self.id or not self.search_cnpj_cpf:
            return

        # Remove caracteres não numéricos
        clean_number = re.sub(r"\D", "", self.search_cnpj_cpf)

        cnpj = clean_number if cnpj_cpf_module.validar_cnpj(clean_number) else False
        cpf = clean_number if cnpj_cpf_module.validar_cpf(clean_number) else False

        if not cnpj and not cpf:
            return

        # Verifica se está completo (14 dígitos para CNPJ ou 11 para CPF)

        fiels = [
            "name",
            "vat",
            "company_type",
            "street",
            "street2",
            "city_id",
            "state_id",
        ]

        # # Se já tem dados cadastrados, pergunta se quer sobrescrever
        # if any(self[field] for field in fiels) and not self._context.get(
        #     "force_autocomplete"
        # ):
        #     return {
        #         "warning": {
        #             "title": _("Parceiro já possui dados"),
        #             "message": _(
        #                 "Este parceiro já possui informações cadastradas. "
        #                 "A consulta automática irá sobrescrever os dados existentes."
        #             ),
        #         }
        #     }

        # return {
        #     "warning": {
        #         "title": _("Consulta realizada com sucesso"),
        #         "message": _(
        #             "Dados obtidos da SEFAZ. Verifique as informações antes de salvar."
        #         ),
        #     }
        # }

        # Realiza a consulta na SEFAZ
        try:
            partner_data = self._consult_sefaz_cadastro(clean_number)
            _logger.info(f"Dados obtidos da SEFAZ: {partner_data}")
            # if partner_data:
            #     # Atualiza os campos do parceiro
            #     self.update(partner_data)
            #     return {
            #         "warning": {
            #             "title": _("Consulta realizada com sucesso"),
            #             "message": _(
            #                 "Dados obtidos da SEFAZ. Verifique as informações antes de salvar."
            #             ),
            #         }
            #     }
        except UserError as e:
            return {"warning": {"title": _("Erro na consulta"), "message": str(e)}}
        except Exception as e:
            _logger.error(f"Erro inesperado na consulta SEFAZ: {str(e)}", exc_info=True)
            return {
                "warning": {
                    "title": _("Erro na consulta"),
                    "message": _(
                        "Erro inesperado ao consultar SEFAZ. Verifique os logs para mais detalhes."
                    ),
                }
            }

    def _get_company_certificate(self):
        """
        Obtém o certificado digital da empresa para autenticação na SEFAZ
        """
        # Busca certificado da empresa do usuário atual
        company = self.env.company

        # Busca certificado A1 válido
        certificate = company.get_nfe_certificate_pkcs12()
        if not certificate:
            raise UserError(
                _(
                    "Nenhum certificado digital válido encontrado para a empresa.\n"
                    "Configure um certificado A1 válido antes de realizar consultas."
                )
            )

        return {
            "cert_file": certificate.cert_file,
            "password": certificate.password,
        }

    def _get_sefaz_endpoint(self, state_code):
        """
        Obtém o endpoint da SEFAZ para consulta de cadastro
        """
        endpoints = get_nfe_endpoint_by_state(state_code)
        if not endpoints:
            raise UserError(
                _(
                    "Estado %s não possui endpoints configurados.\n"
                    "Configure os endpoints em l10n_br_nfe/utils/endpoints.py"
                )
                % state_code
            )

        # Determina ambiente (produção ou homologação)
        company = self.env.company
        environment = (
            "production"
            if company.fiscal_document_emission_env == "1"
            else "homologation"
        )

        endpoint_config = endpoints.get(environment, {}).get("NfeConsultaCadastro")
        if not endpoint_config:
            raise UserError(
                _("Endpoint NfeConsultaCadastro não configurado para %s em ambiente %s")
                % (state_code, environment)
            )

        return endpoint_config["url"]

    def _build_conscad_xml(self, document_number, state_code):
        """
        Constrói o XML de consulta cadastro (ConsCad)

        Args:
            document_number: CNPJ ou CPF (apenas números)
            state_code: Código UF (ex: MG)

        Returns:
            String com XML de consulta
        """
        ns = "http://www.portalfiscal.inf.br/nfe"
        root = etree.Element("{%s}ConsCad" % ns, versao="2.00", nsmap={None: ns})

        # infCons
        inf_cons = etree.SubElement(root, "infCons")

        # xServ
        x_serv = etree.SubElement(inf_cons, "xServ")
        x_serv.text = "CONS-CAD"

        # UF
        uf = etree.SubElement(inf_cons, "UF")
        uf.text = state_code

        # CNPJ ou CPF
        if len(document_number) == 14:
            cnpj = etree.SubElement(inf_cons, "CNPJ")
            cnpj.text = document_number
        else:
            cpf = etree.SubElement(inf_cons, "CPF")
            cpf.text = document_number

        xml_string = etree.tostring(root, encoding="unicode")

        return xml_string

    def _send_soap_request(self, url, xml_content, certificado):
        """
        Envia requisição SOAP para SEFAZ com autenticação por certificado digital

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
            # Envelope SOAP
            soap_env = f"""<?xml version="1.0" encoding="utf-8"?>
<soap:Envelope xmlns:soap="http://www.w3.org/2003/05/soap-envelope" xmlns:cad="http://www.portalfiscal.inf.br/nfe/wsdl/CadConsultaCadastro4">
    <soap:Header/>
    <soap:Body>
        <cad:consultaCadastro>
            <cad:nfeCabecMsg>
                <![CDATA[<?xml version="1.0" encoding="utf-8"?><nfeCabecMsg xmlns="http://www.portalfiscal.inf.br/nfe/wsdl/CadConsultaCadastro4"><versaoDados>2.00</versaoDados></nfeCabecMsg>]]>
            </cad:nfeCabecMsg>
            <cad:nfeDadosMsg>
                <![CDATA[{xml_content}]]>
            </cad:nfeDadosMsg>
        </cad:consultaCadastro>
    </soap:Body>
</soap:Envelope>"""

            headers = {
                "Content-Type": 'application/soap+xml; charset=utf-8; action="http://www.portalfiscal.inf.br/nfe/wsdl/CadConsultaCadastro4/consultaCadastro"',
                "SOAPAction": "http://www.portalfiscal.inf.br/nfe/wsdl/CadConsultaCadastro4/consultaCadastro",
            }

            _logger.info(f"Enviando consulta cadastro para {url}")

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
                    _("Erro ao consultar SEFAZ: HTTP %s") % response.status_code
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

    def _parse_cadastro_response(self, response_xml):
        """
        Faz o parse da resposta XML da consulta cadastro

        Args:
            response_xml: XML de resposta da SEFAZ

        Returns:
            Dict com dados do parceiro
        """
        try:
            # Parse do XML
            root = etree.fromstring(response_xml.encode("utf-8"))

            # Namespaces
            namespaces = {
                "soap": "http://www.w3.org/2003/05/soap-envelope",
                "nfe": "http://www.portalfiscal.inf.br/nfe",
            }

            # Extrair retConsCad do SOAP body
            ret_cons_cad = root.xpath("//nfe:retConsCad", namespaces=namespaces)

            if not ret_cons_cad:
                _logger.error("Elemento retConsCad não encontrado na resposta")
                raise UserError(_("Resposta inválida da SEFAZ"))

            ret_cons_cad = ret_cons_cad[0]

            # Verificar código de status
            c_stat = ret_cons_cad.find("nfe:infCons/nfe:cStat", namespaces)
            x_motivo = ret_cons_cad.find("nfe:infCons/nfe:xMotivo", namespaces)

            if c_stat is not None and c_stat.text != "111":
                # 111 = Consulta cadastro com uma ocorrência
                error_msg = (
                    x_motivo.text if x_motivo is not None else "Erro desconhecido"
                )
                _logger.error(f"Erro SEFAZ: {c_stat.text} - {error_msg}")
                raise UserError(_("SEFAZ retornou erro: %s") % error_msg)

            # Extrair dados cadastrais
            inf_cad = ret_cons_cad.find("nfe:infCons/nfe:infCad", namespaces)

            if inf_cad is None:
                raise UserError(_("Nenhuma informação cadastral encontrada"))

            partner_data = {}

            # Nome/Razão Social
            x_nome = inf_cad.find("nfe:xNome", namespaces)
            if x_nome is not None:
                partner_data["name"] = x_nome.text

            # CNPJ
            cnpj = inf_cad.find("nfe:CNPJ", namespaces)
            if cnpj is not None:
                partner_data["vat"] = cnpj.text
                partner_data["company_type"] = "company"

            # CPF
            cpf = inf_cad.find("nfe:CPF", namespaces)
            if cpf is not None:
                partner_data["vat"] = cpf.text
                partner_data["company_type"] = "person"

            # Inscrição Estadual
            ie = inf_cad.find("nfe:IE", namespaces)
            if ie is not None and ie.text:
                partner_data["l10n_br_ie_code"] = ie.text

            # Endereço
            ender = inf_cad.find("nfe:ender", namespaces)
            if ender is not None:
                # Logradouro
                x_lgr = ender.find("nfe:xLgr", namespaces)
                if x_lgr is not None:
                    partner_data["street"] = x_lgr.text

                # Número
                nro = ender.find("nfe:nro", namespaces)
                if nro is not None:
                    if "street" in partner_data:
                        partner_data["street"] += f", {nro.text}"
                    else:
                        partner_data["street"] = nro.text

                # Complemento
                x_cpl = ender.find("nfe:xCpl", namespaces)
                if x_cpl is not None:
                    partner_data["street2"] = x_cpl.text

                # Bairro
                x_bairro = ender.find("nfe:xBairro", namespaces)
                if x_bairro is not None:
                    partner_data["l10n_br_district"] = x_bairro.text

                # Município (buscar res.city por código IBGE)
                c_mun = ender.find("nfe:cMun", namespaces)
                if c_mun is not None:
                    city = self.env["res.city"].search(
                        [("l10n_br_ibge_code", "=", c_mun.text)], limit=1
                    )
                    if city:
                        partner_data["city_id"] = city.id
                        partner_data["state_id"] = city.state_id.id
                        partner_data["country_id"] = city.country_id.id

                # CEP
                cep = ender.find("nfe:CEP", namespaces)
                if cep is not None:
                    partner_data["zip"] = cep.text

            _logger.info(f"Dados extraídos da consulta cadastro: {partner_data}")
            return partner_data

        except etree.XMLSyntaxError as e:
            _logger.error(f"Erro de sintaxe XML na resposta: {str(e)}")
            raise UserError(_("Erro ao processar resposta da SEFAZ: XML inválido"))
        except Exception as e:
            _logger.error(f"Erro ao fazer parse da resposta: {str(e)}", exc_info=True)
            raise

    def _consult_sefaz_cadastro(self, document_number):
        """
        Consulta o cadastro na SEFAZ usando CNPJ ou CPF

        Args:
            document_number: CNPJ ou CPF (apenas números)

        Returns:
            Dict com dados do parceiro ou None se não encontrado
        """

        company = self.env.company
        # Obter certificado
        certificate = company.get_nfe_certificate_pkcs12()

        # Determinar estado para consulta
        # Por padrão, usa o estado da empresa
        state_code = company.state_id.code

        if not state_code:
            raise UserError(
                _(
                    "Para realizar a consulta, é necessário informar o estado da empresa no cadastro da empresa."
                )
            )

        # Obter endpoint
        url = self._get_sefaz_endpoint(state_code)

        # Construir XML de consulta
        xml_content = self._build_conscad_xml(document_number, state_code)

        _logger.info(f"Consultando cadastro para documento {document_number}")
        _logger.debug(f"XML de consulta:\n{xml_content}")

        # Enviar requisição SOAP
        response = self._send_soap_request(url, xml_content, certificate)

        _logger.debug(f"Resposta SEFAZ:\n{response.text}")

        # Parse da resposta
        partner_data = self._parse_cadastro_response(response.text)

        return partner_data
