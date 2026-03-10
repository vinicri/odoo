from erpbrasil.assinatura import certificado as cert

from odoo import _, api, fields, models
from odoo.exceptions import ValidationError


class ResCompany(models.Model):
    _inherit = "res.company"

    certificate_ecnpj_id = fields.Many2one(
        comodel_name="l10n_br_certificate.certificate",
        string="E-CNPJ",
        domain="[('type', '=', 'e-cnpj')]",
    )

    certificate_nfe_id = fields.Many2one(
        comodel_name="l10n_br_certificate.certificate",
        string="NFe",
        domain="[('type', '=', 'nf-e')]",
    )

    certificate_id = fields.Many2one(
        comodel_name="l10n_br_certificate.certificate",
        compute="_compute_certificate",
    )

    def _compute_certificate(self):
        for record in self:
            certificate = False
            if record.sudo().certificate_nfe_id:
                certificate = record.sudo().certificate_nfe_id
            elif record.sudo().certificate_ecnpj_id:
                certificate = record.sudo().certificate_ecnpj_id

            if not certificate:
                raise ValidationError(
                    _(
                        "Certificate not found, you need to inform your e-CNPJ"
                        " or e-NFe certificate in the Company."
                    )
                )

            record.certificate_id = certificate

    # @api.model
    # def _get_br_ecertificate(self, only_ecnpj=False):
    #     certificate = self.l10n_br_certificate_id
    #     if only_ecnpj:
    #         if certificate != self.sudo().l10n_br_certificate_ecnpj_id:
    #             certificate = self.sudo().l10n_br_certificate_ecnpj_id
    #             if not certificate:
    #                 raise ValidationError(
    #                     _("Only e-CNPJ Certicate can be used for this case.")
    #                 )
    #     return cert.Certificado(
    #         arquivo=certificate.file,
    #         senha=certificate.password,
    #     )

    @api.model
    def get_nfe_certificate(self):
        certificate = self.certificate_nfe_id
        if not certificate:
            raise ValidationError(
                _(
                    "Nenhum certificado NF-e configurado para a empresa %s."
                    "Configure um certificado A1 nas configurações da empresa."
                )
                % self.name
            )
        return cert.Certificado(
            arquivo=certificate.file,
            senha=certificate.password,
        )
