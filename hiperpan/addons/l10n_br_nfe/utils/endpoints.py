# NFe 4.00 endpoints - MG (Minas Gerais)
NFE_ENDPOINTS_BY_STATE = {
    "MG": {
      "production": {
        "NfeInutilizacao": {
            "version": "4.00",
            "url": "https://nfe.fazenda.mg.gov.br/nfe2/services/NFeInutilizacao4",
        },
        "NfeConsultaProtocolo": {
            "version": "4.00",
            "url": "https://nfe.fazenda.mg.gov.br/nfe2/services/NFeConsultaProtocolo4",
        },
        "NfeStatusServico": {
            "version": "4.00",
            "url": "https://nfe.fazenda.mg.gov.br/nfe2/services/NFeStatusServico4",
        },
        "NfeConsultaCadastro": {
            "version": "4.00",
            "url": "https://nfe.fazenda.mg.gov.br/nfe2/services/CadConsultaCadastro4",
        },
        "RecepcaoEvento": {
            "version": "4.00",
            "url": "https://nfe.fazenda.mg.gov.br/nfe2/services/NFeRecepcaoEvento4",
        },
        "NFeAutorizacao": {
            "version": "4.00",
            "url": "https://nfe.fazenda.mg.gov.br/nfe2/services/NFeAutorizacao4",
        },
        "NFeRetAutorizacao": {
            "version": "4.00",
            "url": "https://nfe.fazenda.mg.gov.br/nfe2/services/NFeRetAutorizacao4",
        },
      },
      "homologation": {
        "NfeInutilizacao": {
            "version": "4.00",
            "url": "https://hnfe.fazenda.mg.gov.br/nfe2/services/NFeInutilizacao4",
        },
        "NfeConsultaProtocolo": {
            "version": "4.00",
            "url": "https://hnfe.fazenda.mg.gov.br/nfe2/services/NFeConsultaProtocolo4",
        },
        "NfeStatusServico": {
            "version": "4.00",
            "url": "https://hnfe.fazenda.mg.gov.br/nfe2/services/NFeStatusServico4",
        },
        "NfeConsultaCadastro": {
            "version": "4.00",
            "url": "https://hnfe.fazenda.mg.gov.br/nfe2/services/CadConsultaCadastro4",
        },
        "RecepcaoEvento": {
            "version": "4.00",
            "url": "https://hnfe.fazenda.mg.gov.br/nfe2/services/NFeRecepcaoEvento4",
        },
        "NFeAutorizacao": {
            "version": "4.00",
            "url": "https://hnfe.fazenda.mg.gov.br/nfe2/services/NFeAutorizacao4",
        },
        "NFeRetAutorizacao": {
            "version": "4.00",
            "url": "https://hnfe.fazenda.mg.gov.br/nfe2/services/NFeRetAutorizacao4",
        },
      },
    },
}


def get_nfe_endpoint_by_state(state):
    return NFE_ENDPOINTS_BY_STATE.get(state)
