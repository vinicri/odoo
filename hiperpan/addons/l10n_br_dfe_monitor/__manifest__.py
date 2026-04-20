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
    "depends": ["l10n_br_fiscal", "l10n_br_certificate", "l10n_br_nfe"],
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
        "views/dfe_menu.xml",
    ],
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
