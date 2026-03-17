{
    "name": "Brazilian Partner NFe Autocomplete",
    "version": "1.0",
    "category": "Localization",
    "description": """
        CNPJ/CPF Autocomplete for Brazilian Partners

        This module allows automatic partner data completion by querying
        SEFAZ's NfeConsultaCadastro service using CNPJ or CPF.

        Features:
        - CNPJ/CPF input field on partner form
        - Automatic consultation when number is complete
        - Uses digital certificate for authentication
        - Auto-fills partner data from SEFAZ response
    """,
    "author": "Hiperpan",
    "depends": ["l10n_br_fiscal", "l10n_br_certificate"],
    "license": "LGPL-3",
    "data": [
        "views/res_partner_views.xml",
    ],
    "external_dependencies": {
        "python": ["requests", "cryptography"],
    },
    "installable": True,
    "auto_install": False,
}
