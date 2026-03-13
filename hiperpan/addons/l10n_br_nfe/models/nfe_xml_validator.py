import os

from lxml import etree
from odoo import _
from odoo.exceptions import ValidationError

_schema_cache = {}


def _get_nfe_schema(version="4.00"):
    """Load and cache the XSD schema for the given NF-e version."""
    if version in _schema_cache:
        return _schema_cache[version]

    version_dir = version.replace(".", "_")
    schema_dir = os.path.join(
        os.path.dirname(os.path.dirname(__file__)),
        "schemas",
        "nfe",
        f"v{version_dir}",
    )
    schema_file = os.path.join(schema_dir, f"nfe_v{version}.xsd")

    if not os.path.isfile(schema_file):
        raise FileNotFoundError(
            f"XSD schema not found: {schema_file}"
        )

    with open(schema_file, "rb") as f:
        schema_doc = etree.parse(f)

    schema = etree.XMLSchema(schema_doc)
    _schema_cache[version] = schema
    return schema


def validate_nfe_xml(xml_element, version="4.00"):
    """Validate an NFe XML element tree against the official XSD.

    The ``ds:Signature`` element is required by the ``TNFe`` complex type,
    so this function must be called on the **signed** XML tree.

    Raises ``odoo.exceptions.ValidationError`` with all schema errors on
    failure.
    """
    schema = _get_nfe_schema(version)
    if not schema.validate(xml_element):
        errors = "\n".join(str(e) for e in schema.error_log)
        raise ValidationError(
            _("XML da NF-e não é válido conforme o schema XSD:\n%s") % errors
        )
