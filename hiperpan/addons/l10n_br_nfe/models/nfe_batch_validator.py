"""
Módulo para validação de lote NFe contra schemas XSD
"""
import os
import logging
from lxml import etree
from odoo.exceptions import ValidationError
from odoo import _

_logger = logging.getLogger(__name__)


class NfeBatchValidator:
    """Classe para validação de lote NFe contra XSD"""

    def __init__(self, version="4.00"):
        """
        Inicializa o validador com a versão do schema.

        Args:
            version: Versão do schema NFe (padrão: "4.00")
        """
        self.version = version
        self.schema_dir = self._get_schema_directory()
        self.schema_cache = {}

    def _get_schema_directory(self):
        """
        Retorna o diretório onde os schemas estão armazenados.

        Returns:
            String com o caminho absoluto do diretório de schemas
        """
        # Obter diretório do módulo
        module_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        schema_dir = os.path.join(module_dir, "schemas", f"v{self.version}")

        if not os.path.exists(schema_dir):
            raise ValidationError(
                _(
                    "Diretório de schemas não encontrado: %s\n"
                    "Verifique se os arquivos XSD foram instalados corretamente."
                )
                % schema_dir
            )

        return schema_dir

    def _load_schema(self, schema_name):
        """
        Carrega um schema XSD do diretório de schemas.

        Args:
            schema_name: Nome do arquivo XSD (ex: "enviNFe_v4.00.xsd")

        Returns:
            etree.XMLSchema object
        """
        # Verificar cache
        if schema_name in self.schema_cache:
            return self.schema_cache[schema_name]

        schema_path = os.path.join(self.schema_dir, schema_name)

        if not os.path.exists(schema_path):
            raise ValidationError(
                _("Schema não encontrado: %s") % schema_path
            )

        try:
            # Parse do schema XSD
            with open(schema_path, "rb") as schema_file:
                schema_doc = etree.parse(schema_file)

            # Criar XMLSchema
            schema = etree.XMLSchema(schema_doc)

            # Adicionar ao cache
            self.schema_cache[schema_name] = schema

            _logger.debug(f"Schema {schema_name} carregado com sucesso")
            return schema

        except etree.XMLSchemaParseError as e:
            _logger.error(f"Erro ao fazer parse do schema {schema_name}: {str(e)}")
            raise ValidationError(
                _("Erro ao carregar schema %s: %s") % (schema_name, str(e))
            )

    def validate_batch_xml(self, xml_string):
        """
        Valida o XML do lote (enviNFe) contra o schema XSD.

        Args:
            xml_string: String ou bytes contendo o XML do lote

        Returns:
            True se válido

        Raises:
            ValidationError: Se o XML for inválido
        """
        try:
            # Converter para bytes se necessário
            if isinstance(xml_string, str):
                xml_bytes = xml_string.encode("utf-8")
            else:
                xml_bytes = xml_string

            # Parse do XML
            xml_doc = etree.fromstring(xml_bytes)

            # Carregar schema do enviNFe
            schema = self._load_schema(f"enviNFe_v{self.version}.xsd")

            # Validar contra schema
            if not schema.validate(xml_doc):
                # Coletar todos os erros
                errors = []
                for error in schema.error_log:
                    errors.append(
                        f"Linha {error.line}, Coluna {error.column}: {error.message}"
                    )

                error_message = "\n".join(errors)
                _logger.error(f"Erro de validação XSD do lote:\n{error_message}")

                raise ValidationError(
                    _(
                        "O XML do lote NFe não passou na validação do schema XSD:\n\n%s"
                    )
                    % error_message
                )

            _logger.info("Lote NFe validado com sucesso contra XSD")
            return True

        except etree.XMLSyntaxError as e:
            _logger.error(f"Erro de sintaxe XML: {str(e)}")
            raise ValidationError(
                _("Erro de sintaxe no XML do lote: %s") % str(e)
            )
        except Exception as e:
            _logger.error(f"Erro ao validar lote NFe: {str(e)}")
            raise ValidationError(
                _("Erro ao validar lote NFe: %s") % str(e)
            )

    def validate_nfe_xml(self, xml_string):
        """
        Valida o XML de uma NFe individual contra o schema XSD.

        Args:
            xml_string: String ou bytes contendo o XML da NFe

        Returns:
            True se válido

        Raises:
            ValidationError: Se o XML for inválido
        """
        try:
            # Converter para bytes se necessário
            if isinstance(xml_string, str):
                xml_bytes = xml_string.encode("utf-8")
            else:
                xml_bytes = xml_string

            # Parse do XML
            xml_doc = etree.fromstring(xml_bytes)

            # Carregar schema da NFe
            schema = self._load_schema(f"leiauteNFe_v{self.version}.xsd")

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
                    _(
                        "O XML da NFe não passou na validação do schema XSD:\n\n%s"
                    )
                    % error_message
                )

            _logger.info("NFe validada com sucesso contra XSD")
            return True

        except etree.XMLSyntaxError as e:
            _logger.error(f"Erro de sintaxe XML: {str(e)}")
            raise ValidationError(
                _("Erro de sintaxe no XML da NFe: %s") % str(e)
            )
        except Exception as e:
            _logger.error(f"Erro ao validar NFe: {str(e)}")
            raise ValidationError(
                _("Erro ao validar NFe: %s") % str(e)
            )
