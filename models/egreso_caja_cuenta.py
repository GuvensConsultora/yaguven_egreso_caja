from odoo import _, api, fields, models
from odoo.exceptions import ValidationError


class YaguvenEgresoCajaCuenta(models.Model):
    """Cuentas que se pueden elegir al cargar un egreso de caja.

    Vive en el módulo y no como marca sobre el plan de cuentas, así se desinstala
    sin dejar nada en `account.account`. Nace vacía: mientras nadie habilite una
    cuenta, la pantalla de egresos lo dice en vez de mostrar el plan entero.
    """

    _name = "yaguven.egreso.caja.cuenta"
    _description = "Cuenta habilitada para egresos de caja"
    _order = "sequence, id"

    sequence = fields.Integer(string="Orden", default=10)
    account_id = fields.Many2one(
        "account.account",
        string="Cuenta contable",
        required=True,
        ondelete="cascade",
        check_company=True,
    )
    company_id = fields.Many2one(
        "res.company",
        string="Compañía",
        required=True,
        default=lambda self: self.env.company,
    )
    active = fields.Boolean(
        string="Activa",
        default=True,
        help="Desactivar una cuenta la saca de la lista sin borrar el historial.",
    )
    nota = fields.Char(
        string="Para qué se usa",
        help="Opcional: aclaración de cuándo corresponde elegir esta cuenta.",
    )

    _sql_constraints = [
        (
            "cuenta_unica_por_compania",
            "unique(account_id, company_id)",
            "Esa cuenta ya está habilitada para egresos de caja en esta compañía.",
        ),
    ]

    @api.constrains("account_id", "company_id")
    def _check_cuenta_de_la_compania(self):
        for habilitada in self:
            if habilitada.company_id not in habilitada.account_id.company_ids:
                raise ValidationError(
                    _(
                        "La cuenta «%(cuenta)s» no pertenece a la compañía «%(compania)s».",
                        cuenta=habilitada.account_id.display_name,
                        compania=habilitada.company_id.display_name,
                    )
                )

    @api.depends("account_id")
    def _compute_display_name(self):
        for habilitada in self:
            habilitada.display_name = habilitada.account_id.display_name
