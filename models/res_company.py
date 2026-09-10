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
    yaguven_devolucion_journal_id = fields.Many2one(
        "account.journal",
        string="Caja de las devoluciones",
        check_company=True,
        domain="[('type', 'in', ('cash', 'bank'))]",
        help="Caja por la que sale el dinero cuando se le devuelve a un cliente. "
        "Es la caja del cajero, no la caja central: así la devolución baja del "
        "arqueo de su turno. Nace vacío: sin esto configurado el módulo avisa.",
    )
    yaguven_egreso_caja_aviso_partner_ids = fields.Many2many(
        "res.partner",
        "yaguven_egreso_caja_aviso_rel",
        "company_id",
        "partner_id",
        string="Avisar las devoluciones a",
        help="A quiénes les llega la notificación cada vez que se confirma una "
        "devolución de dinero. Vacío = no se avisa a nadie.",
    )
    yaguven_egreso_caja_account_id = fields.Many2one(
        "account.account",
        string="Caja central a acreditar",
        check_company=True,
        domain="[('account_type', 'in', ('asset_cash', 'asset_current'))]",
        help="Cuenta que se acredita en cada egreso. Es de donde sale el dinero.",
    )
