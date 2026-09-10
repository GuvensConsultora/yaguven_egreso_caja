from odoo import fields, models


class ResConfigSettings(models.TransientModel):
    """Los dos parámetros de la compañía, en Ajustes de Contabilidad.

    Los dominios se repiten acá a propósito: un campo `related` **no hereda el
    dominio** del campo de origen — medido en la instancia, `fields_get` sobre
    `res.config.settings` devolvía `[]` en los dos y la pantalla ofrecía el plan
    de cuentas entero. Y no se puede reusar el mismo texto que en `res.company`,
    porque ahí `id` es la compañía y acá es el registro transitorio de ajustes:
    la compañía que corresponde es `company_id`.
    """

    _inherit = "res.config.settings"

    yaguven_egreso_caja_journal_id = fields.Many2one(
        related="company_id.yaguven_egreso_caja_journal_id",
        string="Diario de egresos de caja",
        readonly=False,
        domain="[('type', 'in', ('cash', 'bank')), ('company_id', '=', company_id)]",
    )
    yaguven_devolucion_journal_id = fields.Many2one(
        related="company_id.yaguven_devolucion_journal_id",
        string="Caja de las devoluciones",
        readonly=False,
        domain="[('type', 'in', ('cash', 'bank')), ('company_id', '=', company_id)]",
    )
    yaguven_egreso_caja_aviso_partner_ids = fields.Many2many(
        related="company_id.yaguven_egreso_caja_aviso_partner_ids",
        string="Avisar las devoluciones a",
        readonly=False,
    )
    yaguven_egreso_caja_account_id = fields.Many2one(
        related="company_id.yaguven_egreso_caja_account_id",
        string="Caja central a acreditar",
        readonly=False,
        domain="[('company_ids', 'in', [company_id]),"
        " ('account_type', 'in', ('asset_cash', 'asset_current'))]",
    )
