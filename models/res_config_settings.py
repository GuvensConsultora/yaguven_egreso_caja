from odoo import fields, models


class ResConfigSettings(models.TransientModel):
    _inherit = "res.config.settings"

    yaguven_egreso_caja_journal_id = fields.Many2one(
        related="company_id.yaguven_egreso_caja_journal_id",
        string="Diario de egresos de caja",
        readonly=False,
    )
    yaguven_egreso_caja_account_id = fields.Many2one(
        related="company_id.yaguven_egreso_caja_account_id",
        string="Caja central a acreditar",
        readonly=False,
    )
