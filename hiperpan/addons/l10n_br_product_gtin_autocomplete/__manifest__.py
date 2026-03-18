{
    "name": "Brazilian Product GTIN Autocomplete",
    "version": "1.0",
    "category": "Inventory",
    "description": """
        GTIN/Barcode Autocomplete for Brazilian Products

        This module allows automatic product data completion by querying
        SEFAZ's Cadastro Centralizado de GTIN (CCG) using GTIN/barcode.

        Features:
        - GTIN search field on product form
        - Automatic consultation when GTIN is entered
        - Uses digital certificate for authentication
        - Auto-fills product data from CCG response (Description, NCM, CEST)
    """,
    "author": "Hiperpan",
    "depends": ["product", "l10n_br_certificate"],
    "license": "LGPL-3",
    "data": [
        "views/product_template_views.xml",
    ],
    "external_dependencies": {
        "python": ["requests", "cryptography"],
    },
    "installable": True,
    "auto_install": False,
}
