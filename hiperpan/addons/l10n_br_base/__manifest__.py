{
    "name": "Hiperpan - Brazilian - Base",
    "version": "1.2",
    "countries": ["br"],
    #'category': 'Accounting/Localizations/Account Charts',
    "description": """
  Base module for the Brazilian localization
  ==========================================
  """,
    "depends": [
        "base",
        "l10n_br",
    ],
    "license": "LGPL-3",
    # "assets": {
    #     "web.assets_backend": [
    #         "l10n_br_base/static/src/js/phone_field.js",
    #     ],
    # },
    "data": [
        "data/res.country.state.csv",
        "data/res.city.csv",
        "views/res_company_views.xml",
        "views/res_partner_views.xml",
    ],
    "external_dependencies": {
        "python": ["erpbrasil.base"],
    },
}
