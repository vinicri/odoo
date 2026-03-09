from odoo import models, fields


class NfeCarrierVolume(models.Model):
    _name = "l10n_br_nfe.nfe.carrier.volume"
    _description = "Volumes transportados da NF-e"

    nfe_document_id = fields.Many2one(
        comodel_name="l10n_br_nfe.nfe.document",
        ondelete="cascade",
        string="NF-e",
    )

    # X27 - Quantidade de volumes transportados (0-1, N, 1-15)
    quantity = fields.Integer(string="Quantidade de Volumes")

    # X28 - Espécie dos volumes transportados (0-1, C, 1-60)
    species = fields.Char(string="Espécie dos Volumes", size=60)

    # X29 - Marca dos volumes transportados (0-1, C, 1-60)
    brand = fields.Char(string="Marca dos Volumes", size=60)

    # X30 - Numeração dos volumes transportados (0-1, C, 1-60)
    numbering = fields.Char(string="Numeração dos Volumes", size=60)

    # X31 - Peso Líquido em kg (0-1, N, 12v3)
    net_weight = fields.Float(string="Peso Líquido (kg)", digits=(12, 3))

    # X32 - Peso Bruto em kg (0-1, N, 12v3)
    gross_weight = fields.Float(string="Peso Bruto (kg)", digits=(12, 3))

    # X33 - Grupo Lacres (0-5000)
    lacre_ids = fields.One2many(
        comodel_name="l10n_br_nfe.nfe.carrier.volume.lacre",
        inverse_name="volume_id",
        string="Lacres",
    )


class NfeCarrierVolumeLacre(models.Model):
    _name = "l10n_br_nfe.nfe.carrier.volume.lacre"
    _description = "Lacres dos volumes transportados da NF-e"

    volume_id = fields.Many2one(
        comodel_name="l10n_br_nfe.nfe.carrier.volume",
        ondelete="cascade",
        string="Volume",
    )

    # X34 - Número do Lacre (C, 1-60)
    number = fields.Char(string="Número do Lacre", size=60, required=True)
