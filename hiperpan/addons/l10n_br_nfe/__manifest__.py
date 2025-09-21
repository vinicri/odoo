{
    "name": "Hiperpan - Nfe",
    "version": "1.0",
    "category": "Localization",
    "description": "Nfe module for Brazil",
    "author": "Hiperpan",
    "depends": ["l10n_br_fiscal"],
    "license": "LGPL-3",
    "data": [
        # security
        "security/nfe_security.xml",
        "security/ir.model.access.csv",
        # views
        "views/nfe_series_views.xml",
        "views/nfe_invalidate_numbers_views.xml",
        "views/nfe_tech_contact_views.xml",
        "views/nfe_operation_nature_views.xml",
        "views/nfe_document.xml",
        "views/uom_views.xml",
        "views/nfe_uom_category_views.xml",
        "views/res_company.xml",
        "views/nfe_menus.xml",
    ],
}
