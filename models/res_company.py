from odoo import fields, models


class ResCompany(models.Model):
    _inherit = "res.company"

    yaguven_egreso_caja_journal_id = fields.Many2one(
        "account.journal",
        string="Diario de egresos de caja",
        check_company=True,
        domain="[('type', 'in', ('cash', 'bank'))]",
        help="Diario donde se registran los egresos de caja. Nace vacío a propósito: "
        "sin esto configurado el módulo avisa en vez de elegir uno por su cuenta.",
    )
    yaguven_egreso_caja_account_id = fields.Many2one(
        "account.account",
        string="Caja central a acreditar",
        check_company=True,
        domain="[('account_type', 'in', ('asset_cash', 'asset_current'))]",
        help="Cuenta que se acredita en cada egreso. Es de donde sale el dinero.",
    )
