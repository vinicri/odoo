"""
Wizard para criar uma nova uom.uom a partir do campo Unidade de Medida do item
de escrituração de NF-e.

Aberto a partir do dropdown do campo `uom_id` (opção "Criar Unidade de
Medida..."). A categoria vem travada na categoria do produto do item (mesma
categoria do `product_uom_id`), pois só é possível converter entre unidades da
mesma categoria. O fator de conversão é opcional (padrão 1.0) e pode ser
alterado pelo usuário; a partir dele o tipo (maior/menor que a referência) é
inferido automaticamente, já que a categoria já possui uma unidade de
referência.
"""

from odoo import api, fields, models, _
from odoo.exceptions import ValidationError


class DfeCreateUomWizard(models.TransientModel):
    _name = "l10n_br_dfe_monitor.create_uom_wizard"
    _description = "Criar Unidade de Medida"

    category_id = fields.Many2one(
        "uom.category",
        string="Categoria",
        required=True,
        readonly=True,
    )
    name = fields.Char(string="Nome")

    nfe_name = fields.Char(
        string="Nome na NFE/NFCE", size=6, help="Nome para documentos fiscais"
    )

    multiplier = fields.Float(
        string="Multiplicador",
        digits=0,
        default=1.0,
        help="Quantas vezes esta unidade é maior que a unidade de referência da categoria: (unidade de referência) * multiplicador = (esta unidade). Por exemplo, se a caixa vem com 10 unidades, o multiplicador é 10. Se a caixa bem com 5KG e a unidade de referência é Grama, o multiplicador é 5000.",
    )

    rounding = fields.Float(
        string="Precisão de Arredondamento",
        digits=0,
        required=True,
        default=0.01,
    )

    # Set after creation so the client can read back the new UoM and assign it
    # to the (possibly unsaved) escrituração item.
    created_uom_id = fields.Many2one(
        "uom.uom",
        string="Unidade Criada",
        readonly=True,
    )

    @api.constrains("factor")
    def _check_factor(self):
        for record in self:
            if record.factor <= 0:
                raise ValidationError(_("O fator de conversão deve ser maior que 0."))

    def action_create_uom(self):
        """Create the uom.uom and store it on the wizard.

        Runs from the client's onRecordSaved, after the wizard record has been
        saved (and its constraints validated). The client reads
        ``created_uom_id`` back to assign it to the escrituração item.
        """
        self.ensure_one()

        if not self.name:
            raise ValidationError(_("O nome da unidade de medida é obrigatório."))

        if not self.nfe_name:
            raise ValidationError(_("O nome na NFE/NFCE é obrigatório."))

        reference_uom = self.env["uom.uom"].search(
            [("category_id", "=", self.category_id.id), ("uom_type", "=", "reference")],
            limit=1,
        )

        # A category should always have exactly one reference unit (enforced by
        # uom.uom itself), but guard anyway: without one there is nothing to
        # express the new factor relative to.
        uom_type = "bigger" if reference_uom and self.multiplier > 1.0 else "smaller"

        uom = self.env["uom.uom"].create(
            {
                "name": self.name,
                "category_id": self.category_id.id,
                "uom_type": uom_type,
                "factor_inv": self.multiplier,
                "rounding": self.rounding,
            }
        )
        self.created_uom_id = uom.id
        return False
