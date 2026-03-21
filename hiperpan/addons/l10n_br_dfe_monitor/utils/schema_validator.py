"""
Módulo para validação de lote NFe contra schemas XSD
"""

import os
import logging
from lxml import etree
from odoo.exceptions import ValidationError
from odoo import _

_logger = logging.getLogger(__name__)

version = "1.01"


def _get_schema_directory():
    """
    Retorna o diretório onde os schemas estão armazenados.

    Returns:
        String com o caminho absoluto do diretório de schemas
    """
    # Obter diretório do módulo
    module_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    schema_dir = os.path.join(module_dir, "schemas")

    if not os.path.exists(schema_dir):
        raise ValidationError(
            _(
                "Diretório de schemas não encontrado: %s\n"
                "Verifique se os arquivos XSD foram instalados corretamente."
            )
            % schema_dir
        )

    return schema_dir


def _load_schema():
    """
    Carrega um schema XSD do diretório de schemas.

    Args:
        schema_name: Nome do arquivo XSD (ex: "distDFeInt_v1.01.xsd")

    Returns:
        etree.XMLSchema object
    """

    schema_dir = _get_schema_directory()
    schema_name = f"distDFeInt_v{version}.xsd"
    schema_path = os.path.join(schema_dir, schema_name)

    if not os.path.exists(schema_path):
        raise ValidationError(_("Schema não encontrado: %s") % schema_path)

    try:
        # Criar um parser que resolva imports/includes relativos ao diretório
        parser = etree.XMLParser()

        # Parse do schema XSD
        with open(schema_path, "rb") as schema_file:
            schema_doc = etree.parse(schema_file, parser)

        # Criar XMLSchema com resolução de schemas importados
        # O lxml vai procurar schemas referenciados no mesmo diretório
        schema = etree.XMLSchema(schema_doc)

        # Adicionar ao cache
        # self.schema_cache[schema_name] = schema

        _logger.debug(f"Schema {schema_name} carregado com sucesso")
        return schema

    except etree.XMLSchemaParseError as e:
        _logger.error(f"Erro ao fazer parse do schema {schema_name}: {str(e)}")
        raise ValidationError(
            _("Erro ao carregar schema %s: %s") % (schema_name, str(e))
        )


def validate_dfe_xml(xml_doc):
    """
    Valida o XML

    Args:
        xml_string: String ou bytes contendo o XML da NFe

    Returns:
        True se válido

    Raises:
        ValidationError: Se o XML for inválido
    """
    try:
        # # Converter para bytes se necessário
        # if isinstance(xml_string, str):
        #     xml_bytes = xml_string.encode("utf-8")
        # else:
        #     xml_bytes = xml_string

        # # Parse do XML
        # xml_doc = etree.fromstring(xml_bytes)

        # Carregar schema da NFe
        schema = _load_schema()

        # Validar contra schema
        if not schema.validate(xml_doc):
            # Coletar todos os erros
            errors = []
            for error in schema.error_log:
                errors.append(
                    f"Linha {error.line}, Coluna {error.column}: {error.message}"
                )

            error_message = "\n".join(errors)
            _logger.error(f"Erro de validação XSD da NFe:\n{error_message}")

            raise ValidationError(
                _("O XML da NFe não passou na validação do schema XSD:\n\n%s")
                % error_message
            )

        _logger.info("NFe validada com sucesso contra XSD")
        return True

    except etree.XMLSyntaxError as e:
        _logger.error(f"Erro de sintaxe XML: {str(e)}")
        raise ValidationError(_("Erro de sintaxe no XML da NFe: %s") % str(e))
    except Exception as e:
        _logger.error(f"Erro ao validar NFe: {str(e)}")
        raise ValidationError(_("Erro ao validar NFe: %s") % str(e))
