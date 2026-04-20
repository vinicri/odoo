{
    "name": "Hiperpan - Nfe",
    "version": "1.0",
    "category": "Localization",
    "description": "Nfe module for Brazil",
    "author": "Hiperpan",
    "depends": ["l10n_br_fiscal", "l10n_br_certificate"],
    "license": "LGPL-3",
    "data": [
        # security
        "security/nfe_security.xml",
        "security/ir.model.access.csv",
        # data
        "data/l10n_br_nfe.nfe.additional_information.csv",
        # views
        "views/nfe_series_views.xml",
        "views/nfe_invalidate_numbers_views.xml",
        "views/nfe_tech_contact_views.xml",
        "views/nfe_operation_nature_views.xml",
        "views/nfe_document.xml",
        "views/nfe_document_line.xml",
        "views/nfe_document_payment.xml",
        "views/nfe_additional_information.xml",
        "views/nfe_document_vehicle_traillers.xml",
        "views/uom_views.xml",
        "views/nfe_uom_category_views.xml",
        "views/res_company.xml",
        "views/res_partner.xml",
        "views/company_marketplace.xml",
        "views/nfe_menus.xml",
    ],
    "external_dependencies": {
        "python": [
            "erpbrasil.base",
            "erpbrasil.assinatura",
            "requests",
            "cryptography",
        ],
    },
    "assets": {
        "web.assets_backend": [
            "l10n_br_nfe/static/src/scss/nfe_form.scss",
            "l10n_br_nfe/static/src/js/utils/focus_utils.js",
            "l10n_br_nfe/static/src/js/utils/total_fields_utils.js",
            "l10n_br_nfe/static/src/js/fields/confirmation_field.js",
            "l10n_br_nfe/static/src/js/fields/ipi_icms_confirmation_field.js",
            "l10n_br_nfe/static/src/js/discount_field.js",
            "l10n_br_nfe/static/src/js/insurance_field.js",
            "l10n_br_nfe/static/src/js/other_expenses_field.js",
        ],
    },
}
