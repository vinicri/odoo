from odoo import models, fields, api


class NfeDocumentVehicleTraillers(models.Model):
    _name = "l10n_br_nfe.nfe.document.vehicle.traillers"
    _description = "Reboques do veículo de transporte"

    nfe_document_id = fields.Many2one(
        comodel_name="l10n_br_nfe.nfe.document",
        ondelete="cascade",
        string="NF-e",
    )

    freight_carrier_id = fields.Many2one(
        comodel_name="res.partner",
        string="Transportadora",
        domain="[('country_id.code', '=', 'BR'), ('is_freight_carrier', '=', True)]",
        help="Transportadora responsável pelo frete.",
    )

    freight_carrier_vehicle_id = fields.Many2one(
        comodel_name="l10n_br_fiscal.freight.carrier.vehicle",
        string="Veículo de transporte",
        domain="[('partner_id', '=', freight_carrier_id ), ('traction', '=', False)]",
    )

    freight_carrier_vehicle_license_plate = fields.Char(
        related="freight_carrier_vehicle_id.license_plate",
        string="Placa do veículo de transporte",
        store=True,
        readonly=True,
    )

    freight_carrier_vehicle_licence_plate_state_code = fields.Char(
        related="freight_carrier_vehicle_id.licence_plate_state_id.code",
        string="Estado da placa do veículo de transporte",
        store=True,
        readonly=True,
    )

    freight_carrier_vehicle_rntrc = fields.Char(
        related="freight_carrier_vehicle_id.rntrc",
        string="RNTRC do veículo de transporte",
        store=True,
        readonly=True,
    )

    freight_carrier_vehicle_wagon_identification = fields.Char(
        related="freight_carrier_vehicle_id.wagon_identification",
        string="Identificação do vagão",
        store=True,
        readonly=True,
    )

    freight_carrier_vehicle_barge_identification = fields.Char(
        related="freight_carrier_vehicle_id.barge_identification",
        string="Identificação da balsa",
        store=True,
        readonly=True,
    )
