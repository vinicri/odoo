from odoo import models, fields, api, _
from odoo.exceptions import ValidationError


class UoM(models.Model):
    _inherit = "uom.uom"

    nfe_name = fields.Char(
        string="Nome na NFE/NFCE Emitida", size=6, help="Name of the UOM for NFE"
    )

    _sql_constraints = [
        (
            "nfe_name_uniq",
            "unique(nfe_name)",
            "O Nome na NFE/NFCE deve ser único entre as unidades de medida.",
        ),
    ]

    @api.constrains("nfe_name")
    def _check_nfe_name_unique(self):
        for uom in self:
            if not uom.nfe_name:
                continue
            duplicate = self.search(
                [
                    ("nfe_name", "=", uom.nfe_name),
                    ("id", "!=", uom.id),
                ],
                limit=1,
            )
            if duplicate:
                raise ValidationError(
                    _(
                        "O Nome na NFE/NFCE '%(nfe_name)s' já está em uso pela "
                        "unidade de medida '%(uom_name)s'. Escolha um valor único.",
                        nfe_name=uom.nfe_name,
                        uom_name=duplicate.name,
                    )
                )
