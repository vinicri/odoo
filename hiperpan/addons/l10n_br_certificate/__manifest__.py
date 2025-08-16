{
  'name': 'Hiperpan - Certificado A1',
  'version': '1.0',
  'countries': ['br'],
  #'category': 'Accounting/Localizations/Account Charts',
  'description': """
  Base module for the Brazilian localization
  ==========================================
  """,
  'depends': [
    'l10n_br_base',
  ],
  'license': 'LGPL-3',
  'data': [
    'security/ir.model.access.csv',
    'views/certificate_view.xml',
    'views/res_company_view.xml',
  ],
  'external_dependencies': {
    'python': [ 'erpbrasil.assinatura>=1.7.0' ],
  },
}