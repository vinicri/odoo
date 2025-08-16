from odoo import models, fields, api
from odoo.exceptions import ValidationError

# Série do Documento Fiscal, preencher com zeros na hipótese de a NF-e não possuir série. Série na faixa:

# - [000-889]: Aplicativo do Contribuinte; Emitente=CNPJ; Assinatura pelo e-CNPJ do contribuinte (procEmi<>1,2);

# - [890-899]: Emissão no site do Fisco (NFA-e - Avulsa); Emitente= CNPJ / CPF; Assinatura pelo e-CNPJ da SEFAZ (procEmi=1);

# - [900-909]: Emissão no site do Fisco (NFA-e); Emitente= CNPJ; Assinatura pelo e-CNPJ da SEFAZ (procEmi=1), ou Assinatura pelo e-CNPJ do contribuinte (procEmi=2);

# - [910-919]: Emissão no site do Fisco (NFA-e); Emitente= CPF; Assinatura pelo e-CNPJ da SEFAZ (procEmi=1), ou Assinatura pelo e-CPF do contribuinte (procEmi=2);

# - [920-969]: Aplicativo do Contribuinte; Emitente=CPF; Assinatura pelo e-CPF do co

DOCUMENT_MODEL = [("55", "NF-e (Modelo 55)"), ("65", "NFC-e (Modelo 65)")]


class NfeSeries(models.Model):
    _name = "l10n_br_nfe.nfe.series"
    _description = "Série do Documento Fiscal"

    name = fields.Char(
        string="Name", compute="_compute_name", store=True, index=True, readonly=True
    )

    series = fields.Integer(
        string="Série do Documento Fiscal",
        required=True,
    )

    company_id = fields.Many2one(
        comodel_name="res.company",
        string="Empresa",
        default=lambda self: self.env.company,
        required=True,
        help="Empresa",
    )

    internal_sequence_id = fields.Many2one(
        comodel_name="ir.sequence",
        domain="[('company_id', '=', company_id)]",
        string="Sequence",
        readonly=True,
    )

    document_model = fields.Selection(
        DOCUMENT_MODEL, string="Modelo do Documento Fiscal", required=True
    )

    invalidate_numbers = fields.One2many(
        comodel_name="l10n_br_nfe.nfe.invalidate.numbers",
        inverse_name="series_id",
        string="Invalidate Numbers",
    )

    is_default_for_document_model = fields.Boolean(
        string="É padrão para o modelo de documento fiscal", default=False
    )

    active = fields.Boolean(string="Ativo", default=True)

    _sql_constraints = [
        (
            "nfe_series_unique",
            "unique(series, company_id, document_model)",
            "Já existe uma série com este número para o modelo de documento selecionado.",
        )
    ]

    @api.model
    def _create_sequence(self, values):
        """Create new no_gap entry sequence for every
        new document serie"""
        sequence = {
            "name": values.get(
                "name",
                f'Fiscal BR  Modelo {values.get("document_model")} Série {values.get("series")}',
            ),
            "implementation": "no_gap",
            "padding": 1,
            "number_increment": 1,
            "company_id": self.env.company.id,
        }
        return self.env["ir.sequence"].create(sequence).id

    # vals_list is a list of dictionaries, each dictionary is a record to create
    @api.constrains("series")
    def _check_series_range(self):
        """Validate that series is within the allowed range for NF-e"""
        for record in self:
            if record.series < 1 or record.series > 889:
                raise ValidationError(
                    "A série do documento fiscal deve estar entre 1 e 889."
                )

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if not vals.get("internal_sequence_id"):
                vals.update({"internal_sequence_id": self._create_sequence(vals)})
            if not vals.get("company_id"):
                vals.update({"company_id": self.env.company.id})
            if vals.get("is_default_for_document_model"):
                self.env["l10n_br_nfe.nfe.series"].search(
                    [
                        ("document_model", "=", vals.get("document_model")),
                        ("company_id", "=", vals.get("company_id")),
                        ("is_default_for_document_model", "=", True),
                    ]
                ).write({"is_default_for_document_model": False})
        return super().create(vals_list)

    # todo Fix this, not working
    # def write(self, vals):
    #     res = super().write(vals)
    #     if self.env.context.get("skip_default_unset"):
    #         return res
    #     self.env["l10n_br_nfe.nfe.series"].search(
    #         [
    #             ("document_model", "=", vals.get("document_model")),
    #             ("company_id", "=", vals.get("company_id")),
    #             ("is_default_for_document_model", "=", True),
    #             ("id", "!=", self.id),
    #         ]
    #     ).with_context(skip_default_unset=True).write(
    #         {"is_default_for_document_model": False}
    #     )
    #     return res

    def _is_invalid_number(self, document_number):
        self.ensure_one()
        document_number = int(document_number)
        # Check if the document number falls within any invalid range
        for invalid in self.invalidate_numbers:
            if invalid.number_start <= document_number <= invalid.number_end:
                return True

        return False

    def next_seq_number(self):
        self.ensure_one()
        document_number = self.internal_sequence_id._next()
        while self._is_invalid_number(document_number):
            document_number = self.internal_sequence_id._next()
        return document_number

    @api.depends("document_model", "series")
    def _compute_display_name(self):
        for record in self:
            record.display_name = (
                f"Modelo {record.document_model} - Série {record.series}"
            )

    @api.depends("document_model", "series")
    def _compute_name(self):
        for record in self:
            record.display_name = (
                f"Modelo {record.document_model} - Série {record.series}"
            )
