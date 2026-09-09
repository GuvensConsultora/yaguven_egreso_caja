from markupsafe import Markup

from odoo import Command, _, api, fields, models
from odoo.exceptions import UserError, ValidationError
from odoo.tools import formatLang
from odoo.tools.misc import html_escape

ESTADOS = [
    ("draft", "Borrador"),
    ("posted", "Confirmado"),
    ("cancel", "Anulado"),
]


class YaguvenEgresoCaja(models.Model):
    """Salida de dinero de la caja central, cargada por una sola persona.

    La pantalla pide cuatro datos y arma el asiento: debita la cuenta elegida y
    acredita la caja central de la compañía. El diario y la cuenta central son
    configuración de la compañía y nacen vacíos: sin eso cargado, el módulo avisa
    en vez de asumir una cuenta.
    """

    _name = "yaguven.egreso.caja"
    _description = "Egreso de caja"
    _inherit = ["mail.thread", "mail.activity.mixin"]
    _order = "date desc, id desc"

    name = fields.Char(
        string="Número",
        default="/",
        copy=False,
        readonly=True,
        index=True,
    )
    date = fields.Date(
        string="Fecha",
        required=True,
        default=fields.Date.context_today,
        tracking=True,
    )
    company_id = fields.Many2one(
        "res.company",
        string="Compañía",
        required=True,
        default=lambda self: self.env.company,
    )
    currency_id = fields.Many2one(
        related="company_id.currency_id",
        string="Moneda",
        readonly=True,
    )
    account_id = fields.Many2one(
        "account.account",
        string="Cuenta a debitar",
        required=True,
        tracking=True,
        check_company=True,
        help="Sólo aparecen las cuentas habilitadas para egresos de caja.",
    )
    cuenta_habilitada_ids = fields.Many2many(
        "account.account",
        string="Cuentas habilitadas",
        compute="_compute_cuenta_habilitada_ids",
        help="Campo técnico: alimenta la lista del campo «Cuenta a debitar».",
    )
    amount = fields.Monetary(
        string="Importe",
        required=True,
        currency_field="currency_id",
        tracking=True,
    )
    concepto = fields.Char(
        string="Concepto",
        required=True,
        tracking=True,
        help="Se escribe en el asiento y queda en el historial.",
    )
    recibe_partner_id = fields.Many2one(
        "res.partner",
        string="Recibe (contacto)",
        tracking=True,
        help="Para empleados o proveedores que ya están cargados como contacto. "
        "Si quien retira no está en la lista, dejarlo vacío y escribir el nombre al lado.",
    )
    recibe_nombre = fields.Char(
        string="Recibe (nombre)",
        tracking=True,
        help="Sólo si no se eligió un contacto. Si los dos quedan vacíos, el comprobante "
        "sale con la línea en blanco para completar a mano.",
    )
    recibe_documento = fields.Char(
        string="Documento de quien recibe",
        tracking=True,
        help="Opcional. Si se eligió un contacto y esto queda vacío, se imprime el CUIT del contacto.",
    )
    receptor = fields.Char(
        string="Quien recibe",
        compute="_compute_receptor",
        help="Campo técnico: es lo que se imprime en el comprobante.",
    )
    receptor_documento = fields.Char(
        string="Documento impreso",
        compute="_compute_receptor",
        help="Campo técnico: es lo que se imprime en el comprobante.",
    )
    attachment_ids = fields.Many2many(
        "ir.attachment",
        "yaguven_egreso_caja_attachment_rel",
        "egreso_id",
        "attachment_id",
        string="Comprobante",
        help="Opcional: foto del ticket, remito o recibo.",
    )
    move_id = fields.Many2one(
        "account.move",
        string="Asiento",
        readonly=True,
        copy=False,
        ondelete="restrict",
    )
    reversal_move_id = fields.Many2one(
        "account.move",
        string="Asiento de anulación",
        readonly=True,
        copy=False,
        ondelete="restrict",
    )
    state = fields.Selection(
        ESTADOS,
        string="Estado",
        default="draft",
        required=True,
        copy=False,
        tracking=True,
    )

    # ------------------------------------------------------------------
    # cómputos y validaciones
    # ------------------------------------------------------------------

    @api.depends("recibe_partner_id", "recibe_nombre", "recibe_documento")
    def _compute_receptor(self):
        """Lo que se imprime: manda el contacto y el texto libre es el respaldo.

        Los dos pueden quedar vacíos a propósito — el comprobante sale con la línea
        en blanco y la persona la completa al firmar.
        """
        for egreso in self:
            egreso.receptor = (
                egreso.recibe_partner_id.name or egreso.recibe_nombre or ""
            )
            egreso.receptor_documento = (
                egreso.recibe_documento or egreso.recibe_partner_id.vat or ""
            )

    @api.depends("company_id")
    def _compute_cuenta_habilitada_ids(self):
        for egreso in self:
            habilitadas = self.env["yaguven.egreso.caja.cuenta"].search(
                [("company_id", "=", egreso.company_id.id), ("active", "=", True)]
            )
            egreso.cuenta_habilitada_ids = habilitadas.account_id

    @api.constrains("amount")
    def _check_amount(self):
        for egreso in self:
            if egreso.currency_id.compare_amounts(egreso.amount, 0.0) <= 0:
                raise ValidationError(_("El importe tiene que ser mayor a cero."))

    @api.constrains("account_id", "company_id")
    def _check_cuenta_habilitada(self):
        for egreso in self:
            if egreso.account_id and egreso.account_id not in egreso.cuenta_habilitada_ids:
                raise ValidationError(
                    _(
                        "La cuenta «%(cuenta)s» no está habilitada para egresos de caja "
                        "en esta compañía.",
                        cuenta=egreso.account_id.display_name,
                    )
                )

    # ------------------------------------------------------------------
    # botones
    # ------------------------------------------------------------------

    def action_confirmar(self):
        """Arma el asiento, lo postea y deja el egreso confirmado."""
        for egreso in self:
            if egreso.state != "draft":
                raise UserError(_("Este egreso ya fue confirmado o anulado."))
            diario, cuenta_central = egreso._configuracion_de_la_compania()
            if egreso.name == "/":
                egreso.name = (
                    self.env["ir.sequence"]
                    .with_company(egreso.company_id)
                    .next_by_code("yaguven.egreso.caja")
                    or "/"
                )
            asiento = (
                self.env["account.move"]
                .with_company(egreso.company_id)
                .create(egreso._valores_del_asiento(diario, cuenta_central))
            )
            asiento.action_post()
            egreso.write({"move_id": asiento.id, "state": "posted"})
            egreso._avisar_en_el_historial(
                titulo=_("Egreso confirmado"),
                asiento=asiento,
            )
        return True

    def action_anular(self):
        """Revierte el asiento y deja el egreso anulado, sin borrar nada."""
        for egreso in self:
            if egreso.state != "posted":
                raise UserError(_("Sólo se puede anular un egreso confirmado."))
            reverso = egreso.move_id._reverse_moves(
                [
                    {
                        "date": fields.Date.context_today(egreso),
                        "ref": _("Anulación de %(numero)s", numero=egreso.name),
                    }
                ],
                cancel=True,
            )
            egreso.write({"reversal_move_id": reverso.id, "state": "cancel"})
            egreso._avisar_en_el_historial(
                titulo=_("Egreso anulado"),
                asiento=reverso,
            )
        return True

    def action_ver_asiento(self):
        self.ensure_one()
        asiento = self.reversal_move_id or self.move_id
        if not asiento:
            raise UserError(_("Este egreso todavía no tiene asiento."))
        return {
            "type": "ir.actions.act_window",
            "res_model": "account.move",
            "res_id": asiento.id,
            "view_mode": "form",
            "name": _("Asiento del egreso"),
        }

    # ------------------------------------------------------------------
    # internos
    # ------------------------------------------------------------------

    def _configuracion_de_la_compania(self):
        """Devuelve (diario, cuenta central) o explica qué falta configurar."""
        self.ensure_one()
        compania = self.company_id
        diario = compania.sudo().yaguven_egreso_caja_journal_id
        cuenta_central = compania.sudo().yaguven_egreso_caja_account_id
        if not diario or not cuenta_central:
            raise UserError(
                _(
                    "Falta configurar los egresos de caja de la compañía «%(compania)s».\n\n"
                    "En Ajustes → Contabilidad → Egresos de caja hay que elegir el diario "
                    "y la cuenta de caja central que se acredita.",
                    compania=compania.display_name,
                )
            )
        return diario, cuenta_central

    def _valores_del_asiento(self, diario, cuenta_central):
        self.ensure_one()
        return {
            "move_type": "entry",
            "journal_id": diario.id,
            "date": self.date,
            "ref": "%s - %s" % (self.name, self.concepto),
            "company_id": self.company_id.id,
            "line_ids": [
                Command.create(
                    {
                        "name": self.concepto,
                        "account_id": self.account_id.id,
                        "debit": self.amount,
                        "credit": 0.0,
                    }
                ),
                Command.create(
                    {
                        "name": self.concepto,
                        "account_id": cuenta_central.id,
                        "debit": 0.0,
                        "credit": self.amount,
                    }
                ),
            ],
        }

    def _avisar_en_el_historial(self, titulo, asiento):
        self.ensure_one()
        cuerpo = (
            "<p><strong>%s</strong></p>"
            "<p>Asiento: %s<br/>"
            "Cuenta debitada: %s<br/>"
            "Importe: %s</p>"
        ) % (
            html_escape(titulo),
            html_escape(asiento.display_name),
            html_escape(self.account_id.display_name),
            html_escape(formatLang(self.env, self.amount, currency_obj=self.currency_id)),
        )
        self.message_post(
            body=Markup(cuerpo),
            subject=titulo,
            message_type="comment",
            subtype_xmlid="mail.mt_note",
        )

    @api.ondelete(at_uninstall=False)
    def _impedir_borrado(self):
        for egreso in self:
            if egreso.state != "draft":
                raise UserError(
                    _(
                        "Un egreso confirmado no se borra: se anula, así queda el rastro.\n"
                        "Egreso %(numero)s.",
                        numero=egreso.name,
                    )
                )
