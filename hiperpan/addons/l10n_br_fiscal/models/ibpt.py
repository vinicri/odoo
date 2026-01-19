# Copyright (C) 2024
# License AGPL-3 - See http://www.gnu.org/licenses/agpl-3.0.html

import csv
import base64
import logging
from datetime import datetime

from odoo import _, api, fields, models
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)


# TODO: possivelmente deve-se adicionar a empresa, dado que a tabela do IBPT é gerada para cada empresa.


class Ibpt(models.Model):
    _name = "l10n_br_fiscal.ibpt"
    _description = "IBPT - Tax Estimates"
    _order = "type, code, ex_tipi"

    code = fields.Char(
        string="NCM/NBS Code",
        required=True,
        index=True,
        help="NCM code for products or NBS code for services",
    )

    ex_tipi = fields.Char(
        string="Exception TIPI",
        help="Exception code from TIPI table",
    )

    type = fields.Selection(
        selection=[
            ("0", "Product (NCM)"),
            ("1", "Service (NBS)"),
            ("2", "Other services"),
        ],
        string="Type",
        required=True,
        default="0",
    )

    description = fields.Text(
        string="Description",
    )

    federal_national = fields.Float(
        string="Federal National (%)",
        digits=(3, 2),
        help="Federal tax rate for national products/services",
    )

    federal_imported = fields.Float(
        string="Federal Imported (%)",
        digits=(3, 2),
        help="Federal tax rate for imported products",
    )

    state_tax = fields.Float(
        string="State Tax (%)",
        digits=(3, 2),
        help="State tax rate (ICMS)",
    )

    municipal_tax = fields.Float(
        string="Municipal Tax (%)",
        digits=(3, 2),
        help="Municipal tax rate (ISS)",
    )

    state_id = fields.Many2one(
        comodel_name="res.country.state",
        string="State (UF)",
        domain="[('country_id.code', '=', 'BR')]",
        required=True,
        index=True,
        help="Brazilian state this tax estimate applies to",
    )

    validity_start = fields.Date(
        string="Validity Start",
        help="Start date of validity period",
    )

    validity_end = fields.Date(
        string="Validity End",
        help="End date of validity period",
    )

    key = fields.Char(
        string="Key",
        help="IBPT key for verification",
    )

    version = fields.Char(
        string="Version",
        index=True,
        help="IBPT table version",
    )

    source = fields.Char(
        string="Source",
        help="Data source (IBPT/empresometro.com.br)",
    )

    ncm_id = fields.Many2one(
        comodel_name="l10n_br_fiscal.ncm",
        string="NCM",
        compute="_compute_ncm_id",
        store=True,
        help="Related NCM record",
    )

    active = fields.Boolean(
        default=True,
    )

    _sql_constraints = [
        (
            "ibpt_code_state_ex_uniq",
            "unique (code, state_id, ex_tipi)",
            _("IBPT record already exists for this code, state, and exception!"),
        )
    ]

    @api.depends("code")
    def _compute_ncm_id(self):
        for record in self:
            if record.code and record.type == "0":
                ncm = self.env["l10n_br_fiscal.ncm"].search(
                    [("code_unmasked", "=", record.code)], limit=1
                )
                record.ncm_id = ncm.id if ncm else False
            else:
                record.ncm_id = False

    def name_get(self):
        result = []
        for record in self:
            name = f"{record.code}"
            if record.ex_tipi:
                name += f" (Ex: {record.ex_tipi})"
            if record.state_id:
                name += f" - {record.state_id.code}"
            result.append((record.id, name))
        return result

    @api.model
    def get_ibpt_values(self, ncm_code, state_code, ex_tipi=None):
        """
        Get IBPT tax rates for a given NCM code and state.

        Args:
            ncm_code: NCM code (can be masked or unmasked)
            state_code: State code (UF - 2 letters)
            ex_tipi: Optional exception TIPI code

        Returns:
            dict with tax rates or False if not found
        """
        code_unmasked = "".join(filter(str.isdigit, str(ncm_code)))

        domain = [
            ("code", "=", code_unmasked),
            ("state_id.code", "=", state_code.upper()),
            ("active", "=", True),
        ]

        if ex_tipi:
            domain.append(("ex_tipi", "=", ex_tipi))
        else:
            domain.append("|")
            domain.append(("ex_tipi", "=", False))
            domain.append(("ex_tipi", "=", ""))

        # Get the most recent valid record
        today = fields.Date.today()
        record = self.search(
            domain
            + [
                ("validity_end", ">=", today),
            ],
            order="validity_start desc",
            limit=1,
        )

        # Fallback: if no record found, search for generic NCM 00000000 for the same state
        if not record:
            fallback_domain = [
                ("code", "=", "00000000"),
                ("state_id.code", "=", state_code.upper()),
                ("active", "=", True),
                "|",
                ("ex_tipi", "=", False),
                ("ex_tipi", "=", ""),
            ]
            record = self.search(
                fallback_domain
                + [
                    ("validity_end", ">=", today),
                ],
                order="validity_start desc",
                limit=1,
            )

        if record:
            return {
                "nacional": record.federal_national,
                "importado": record.federal_imported,
                "estadual": record.state_tax,
                "municipal": record.municipal_tax,
                "fonte": record.source,
                "chave": record.key,
                "versao": record.version,
                "vigencia_inicio": record.validity_start,
                "vigencia_fim": record.validity_end,
            }
        return False


class IbptImportWizard(models.TransientModel):
    _name = "l10n_br_fiscal.ibpt.import.wizard"
    _description = "IBPT Import Wizard"

    file = fields.Binary(
        string="IBPT CSV File",
        required=True,
        help="Upload the IBPT CSV file (TabelaIBPTax*.csv)",
    )

    filename = fields.Char(
        string="Filename",
    )

    state_id = fields.Many2one(
        comodel_name="res.country.state",
        string="State (UF)",
        domain="[('country_id.code', '=', 'BR')]",
        required=True,
        help="Select the state for this IBPT table",
    )

    replace_existing = fields.Boolean(
        string="Replace Existing Records",
        default=True,
        help="If checked, existing records for the same state will be deactivated",
    )

    def _parse_date(self, date_str):
        """Parse date from DD/MM/YYYY format."""
        if not date_str:
            return False
        try:
            return datetime.strptime(date_str, "%d/%m/%Y").date()
        except ValueError:
            return False

    def _parse_float(self, value_str):
        """Parse float value, handling Brazilian decimal format."""
        if not value_str:
            return 0.0
        try:
            # Handle Brazilian format (comma as decimal separator)
            return float(value_str.replace(",", "."))
        except ValueError:
            return 0.0

    def action_import(self):
        """Import IBPT data from CSV file."""
        self.ensure_one()

        if not self.file:
            raise UserError(_("Please select a file to import."))

        # Decode the file
        try:
            file_content = base64.b64decode(self.file).decode("utf-8-sig")
        except UnicodeDecodeError:
            try:
                file_content = base64.b64decode(self.file).decode("latin-1")
            except Exception as e:
                raise UserError(_("Error decoding file: %s") % str(e))

        # Parse CSV
        lines = file_content.split("\n")
        if not lines:
            raise UserError(_("Empty file."))

        # Detect delimiter (usually ; for IBPT files)
        first_line = lines[0]
        delimiter = ";" if ";" in first_line else ","

        reader = csv.DictReader(lines, delimiter=delimiter)

        # If replace_existing, delete old records for this state
        # (we must delete, not just deactivate, due to unique constraint)
        if self.replace_existing:
            existing = self.env["l10n_br_fiscal.ibpt"].search(
                [
                    ("state_id", "=", self.state_id.id),
                ]
            )
            if existing:
                existing_count = len(existing)
                existing.unlink()
                _logger.info(
                    f"Deleted {existing_count} existing IBPT records for {self.state_id.code}"
                )

        # Prepare records for batch creation
        # Use a dict to handle duplicates in the CSV (keep last occurrence)
        records_dict = {}
        count = 0
        errors = []

        for row in reader:
            try:
                # Map CSV columns to model fields
                # CSV: codigo;ex;tipo;descricao;nacionalfederal;importadosfederal;estadual;municipal;vigenciainicio;vigenciafim;chave;versao;fonte
                code = row.get("codigo", "").strip()
                if not code:
                    continue

                ex_tipi = row.get("ex", "").strip() or False

                record_vals = {
                    "code": code,
                    "ex_tipi": ex_tipi,
                    "type": row.get("tipo", "0").strip(),
                    "description": (
                        row.get("descricao", "").strip().strip('"')[:255]
                        if row.get("descricao")
                        else ""
                    ),
                    "federal_national": self._parse_float(
                        row.get("nacionalfederal", "0")
                    ),
                    "federal_imported": self._parse_float(
                        row.get("importadosfederal", "0")
                    ),
                    "state_tax": self._parse_float(row.get("estadual", "0")),
                    "municipal_tax": self._parse_float(row.get("municipal", "0")),
                    "validity_start": self._parse_date(row.get("vigenciainicio", "")),
                    "validity_end": self._parse_date(row.get("vigenciafim", "")),
                    "key": row.get("chave", "").strip(),
                    "version": row.get("versao", "").strip(),
                    "source": row.get("fonte", "").strip(),
                    "state_id": self.state_id.id,
                    "active": True,
                }

                # Use (code, ex_tipi) as key to handle duplicates
                key = (code, ex_tipi or "")
                records_dict[key] = record_vals
                count += 1

            except Exception as e:
                errors.append(f"Row {count + 1}: {str(e)}")
                if len(errors) > 10:
                    errors.append("... (more errors truncated)")
                    break

        # Convert dict to list
        records_to_create = list(records_dict.values())
        total_records = len(records_to_create)

        # Batch create records
        batch_size = 1000
        created_count = 0
        for i in range(0, total_records, batch_size):
            batch = records_to_create[i : i + batch_size]
            try:
                self.env["l10n_br_fiscal.ibpt"].create(batch)
                created_count += len(batch)
                _logger.info(
                    f"Imported {created_count}/{total_records} IBPT records..."
                )
            except Exception as e:
                errors.append(f"Batch {i // batch_size + 1}: {str(e)}")
                _logger.error(f"Error creating IBPT batch: {str(e)}")

        _logger.info(
            f"IBPT import completed: {created_count} records imported for {self.state_id.code}"
        )

        message = _("Successfully imported %d IBPT records for %s.") % (
            created_count,
            self.state_id.name,
        )
        if errors:
            message += "\n\n" + _("Errors:") + "\n" + "\n".join(errors[:10])

        return {
            "type": "ir.actions.client",
            "tag": "display_notification",
            "params": {
                "title": _("IBPT Import"),
                "message": message,
                "type": "success" if not errors else "warning",
                "sticky": False,
            },
        }
