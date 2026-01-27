from odoo import models, fields, api


class FreightCarrierVehicle(models.Model):
    _name = "l10n_br_fiscal.freight.carrier.vehicle"
    _description = "Veículo de transporte"
    _rec_name = "license_plate"

    partner_id = fields.Many2one(
        comodel_name="res.partner",
        string="Transportadora",
        domain="[('country_id.code', '=', 'BR'), ('is_freight_carrier', '=', True)]",
    )

    description = fields.Char(
        string="Descrição",
        help="Descrição do veículo, opicional, para facilitar a identificação no sistema apenas.",
    )

    license_plate = fields.Char(string="Placa", required=True)

    licence_plate_state_id = fields.Many2one(
        comodel_name="res.country.state",
        string="Estado da placa",
        domain="[('country_id.code', '=', 'BR')]",
    )

    # Registro Nacional de Transportadores Rodoviários de Carga (RNTRC)
    rntrc = fields.Char(string="RNTRC")

    traction = fields.Boolean(
        string="Tração",
        required=True,
        default=True,
    )

    # identificação do vagão
    wagon_identification = fields.Char(string="Identificação do vagão")

    # identificação da balsa
    barge_identification = fields.Char(string="Identificação da balsa")
