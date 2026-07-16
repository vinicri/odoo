{
    "name": "Brazilian DFe Monitor",
    "version": "1.0",
    "category": "Localization",
    "description": """
        Monitor de Documentos Fiscais Eletrônicos (DFe)

        Consulta e armazena DFes de interesse da empresa via serviço
        NFeDistribuicaoDFe do Ambiente Nacional da SEFAZ.

        Funcionalidades:
        - Consulta DFes a partir do último NSU recebido (distNSU)
        - Consulta DFe por NSU específico (consNSU)
        - Consulta NF-e por chave de acesso (consChNFe)
        - Armazenamento e visualização dos documentos recebidos
        - Suporte a ambientes de produção e homologação
    """,
    "author": "Hiperpan",
    "depends": [
        "l10n_br_base",
        "l10n_br_fiscal",
        "l10n_br_certificate",
        "l10n_br_nfe",
        "stock",
        "uom",
        "point_of_sale",
    ],
    "license": "LGPL-3",
    "data": [
        "security/ir.model.access.csv",
        "views/dfe_document_views.xml",
        "views/dfe_res_nfe_views.xml",
        "views/dfe_proc_nfe_views.xml",
        "views/dfe_proc_evento_nfe_views.xml",
        "wizard/dfe_query_wizard_views.xml",
        "wizard/dfe_upload_wizard_views.xml",
        "wizard/dfe_xml_viewer_wizard_views.xml",
        "wizard/dfe_manifestacao_nao_realizada_wizard_views.xml",
        "wizard/dfe_create_partner_wizard_views.xml",
        "wizard/dfe_create_product_wizard_views.xml",
        "wizard/dfe_download_xml_wizard_views.xml",
        "wizard/dfe_create_uom_wizard_views.xml",
        "wizard/dfe_price_calculator_wizard_views.xml",
        "views/dfe_nfe_escrit.xml",
        "views/dfe_nfe_escrit_item.xml",
        "views/dfe_nfe_escrit_item_defaults.xml",
        "views/cfop_escrit_from_to_views.xml",
        "views/cst_escrit_from_to_views.xml",
        "views/dfe_menu.xml",
        "data/l10n_br_dfe_monitor.cfop_escrit_from_to.csv",
        "data/l10n_br_dfe_monitor.cst_escrit_from_to.csv",
        "views/uom_views.xml",
        "views/res_company_views.xml",
    ],
    "assets": {
        "web.assets_backend": [
            "l10n_br_dfe_monitor/static/src/js/escrit_default_reconcile.js",
            "l10n_br_dfe_monitor/static/src/js/create_product_button.js",
            "l10n_br_dfe_monitor/static/src/xml/create_product_button.xml",
            "l10n_br_dfe_monitor/static/src/js/create_uom_widget.js",
            "l10n_br_dfe_monitor/static/src/js/product_image_search.js",
            "l10n_br_dfe_monitor/static/src/xml/product_image_search.xml",
            "l10n_br_dfe_monitor/static/src/js/product_name_search_widget.js",
            "l10n_br_dfe_monitor/static/src/js/price_calculator_button.js",
            "l10n_br_dfe_monitor/static/src/xml/price_calculator_button.xml",
        ],
    },
    "external_dependencies": {
        "python": [
            "requests",
            "cryptography",
            "erpbrasil.base",
            "erpbrasil.assinatura",
        ],
    },
    "installable": True,
    "auto_install": False,
}
