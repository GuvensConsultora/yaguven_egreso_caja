from markupsafe import Markup

try:                                   # Odoo lo trae, pero no rompemos si falta
    from num2words import num2words
except ImportError:
    num2words = None

from odoo import Command, _, api, fields, models
from odoo.exceptions import UserError, ValidationError
from odoo.tools import formatLang
from odoo.tools.misc import html_escape

ESTADOS = [
    ("draft", "Borrador"),
    ("posted", "Confirmado"),
    ("cancel", "Anulado"),
]

TIPOS = [
    ("gasto", "Gasto de caja"),
    ("devolucion", "Devolución a cliente"),
]


class YaguvenEgresoCaja(models.Model):
    """Salida de dinero de la caja, en dos formas.

    **Gasto de caja**: debita la cuenta que se elige y acredita la caja central.
    El diario y la cuenta central son configuración de la compañía y nacen
    vacíos: sin eso cargado, el módulo avisa en vez de asumir una cuenta.

    **Devolución a cliente**: devuelve dinero que el cliente había pagado de
    más. No se elige cuenta contable: se elige el **saldo a favor** concreto que
    se le devuelve, y el sistema registra un pago de salida en la caja del
    cajero y lo aplica contra ese saldo. Si el cliente no tiene saldo a favor no
    hay nada que devolver — el crédito nace de una nota de crédito, que la
    autoriza quien corresponda antes de que el dinero salga de la caja.
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
    tipo = fields.Selection(
        TIPOS,
        string="Tipo",
        default="gasto",
        required=True,
        tracking=True,
        help="«Gasto de caja» imputa a una cuenta contable. «Devolución a "
        "cliente» devuelve un saldo a favor concreto.",
    )
    cliente_id = fields.Many2one(
        "res.partner",
        string="Cliente",
        tracking=True,
        help="A quién se le devuelve el dinero.",
    )
    credito_line_id = fields.Many2one(
        "account.move.line",
        string="Saldo a favor a devolver",
        copy=False,
        help="El cobro o la nota de crédito que dejó saldo a favor del cliente.",
    )
    credito_disponible_ids = fields.Many2many(
        "account.move.line",
        "yaguven_egreso_caja_credito_rel",
        "egreso_id",
        "line_id",
        string="Saldos a favor del cliente",
        compute="_compute_credito_disponible",
        help="Campo técnico: alimenta la lista del campo «Saldo a favor a devolver».",
    )
    credito_disponible = fields.Monetary(
        string="Total a favor",
        currency_field="currency_id",
        compute="_compute_credito_disponible",
    )
    credito_residual = fields.Monetary(
        string="Disponible en el saldo elegido",
        currency_field="currency_id",
        compute="_compute_credito_residual",
    )
    payment_id = fields.Many2one(
        "account.payment",
        string="Pago de la devolución",
        readonly=True,
        copy=False,
        ondelete="restrict",
    )
    account_id = fields.Many2one(
        "account.account",
        string="Cuenta a debitar",
        tracking=True,
        check_company=True,
        help="Sólo aparecen las cuentas habilitadas para egresos de caja. "
        "En una devolución no se usa: la cuenta la resuelve el sistema.",
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

    def importe_en_letras(self):
        """El importe escrito, para el comprobante que se firma.

        `currency_id.amount_to_text()` devuelve «Cuarenta Y Cinco Mil Peso»
        —capitalizado palabra por palabra y la moneda en singular—, que en un
        papel que alguien firma queda mal. Acá sale «Son pesos cuarenta y cinco
        mil con 00/100», que es la forma usual del recibo.
        """
        self.ensure_one()
        entero = int(abs(self.amount))
        centavos = int(round((abs(self.amount) - entero) * 100))
        if num2words is None:
            return self.currency_id.amount_to_text(self.amount)
        moneda = (self.currency_id.currency_unit_label or "pesos").lower()
        if not moneda.endswith("s"):
            moneda += "s"
        return "Son %s %s con %02d/100" % (moneda, num2words(entero, lang="es"), centavos)

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

    @api.depends("cliente_id", "company_id", "tipo")
    def _compute_credito_disponible(self):
        """Los saldos a favor del cliente, que es lo único que se puede devolver.

        Un saldo a favor es un apunte de su cuenta de deudores con residual
        negativo: un cobro que superó la factura, o una nota de crédito sin
        aplicar. Se leen con `sudo` porque el cajero no tiene permiso sobre la
        contabilidad, pero sí tiene que poder elegir el crédito.
        """
        Linea = self.env["account.move.line"].sudo()
        for egreso in self:
            if egreso.tipo != "devolucion" or not egreso.cliente_id:
                egreso.credito_disponible_ids = False
                egreso.credito_disponible = 0.0
                continue
            lineas = Linea.search([
                ("partner_id", "=", egreso.cliente_id.id),
                ("company_id", "=", egreso.company_id.id),
                ("account_id.account_type", "=", "asset_receivable"),
                ("parent_state", "=", "posted"),
                ("amount_residual", "<", 0),
            ])
            egreso.credito_disponible_ids = lineas
            egreso.credito_disponible = -sum(lineas.mapped("amount_residual"))

    @api.depends("credito_line_id")
    def _compute_credito_residual(self):
        for egreso in self:
            linea = egreso.credito_line_id.sudo()
            egreso.credito_residual = -linea.amount_residual if linea else 0.0

    @api.onchange("tipo")
    def _onchange_tipo(self):
        """Limpia los campos del otro tipo, para que no queden datos colgados."""
        if self.tipo == "devolucion":
            self.account_id = False
        else:
            self.cliente_id = False
            self.credito_line_id = False

    @api.onchange("cliente_id")
    def _onchange_cliente_id(self):
        self.credito_line_id = False
        if self.cliente_id and not self.recibe_partner_id:
            self.recibe_partner_id = self.cliente_id

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

    @api.constrains("tipo", "account_id", "cliente_id", "credito_line_id", "amount")
    def _check_datos_del_tipo(self):
        """Cada tipo exige sus propios datos, y la devolución exige el crédito."""
        for egreso in self:
            if egreso.tipo == "gasto":
                if not egreso.account_id:
                    raise ValidationError(_("Hay que elegir la cuenta a debitar."))
                continue
            if not egreso.cliente_id:
                raise ValidationError(_("Hay que elegir el cliente al que se le devuelve."))
            if not egreso.credito_line_id:
                raise ValidationError(
                    _(
                        "Hay que elegir cuál saldo a favor se devuelve. Si el cliente "
                        "no tiene ninguno, primero hay que hacer la nota de crédito: "
                        "sin crédito registrado no hay nada que devolver."
                    )
                )
            disponible = -egreso.credito_line_id.sudo().amount_residual
            if egreso.currency_id.compare_amounts(egreso.amount, disponible) > 0:
                raise ValidationError(
                    _(
                        "El importe a devolver (%(importe)s) es mayor que el saldo a "
                        "favor elegido (%(disponible)s).",
                        importe=formatLang(self.env, egreso.amount, currency_obj=egreso.currency_id),
                        disponible=formatLang(self.env, disponible, currency_obj=egreso.currency_id),
                    )
                )

    @api.constrains("account_id", "company_id")
    def _check_cuenta_habilitada(self):
        for egreso in self:
            if egreso.tipo == "gasto" and egreso.account_id and egreso.account_id not in egreso.cuenta_habilitada_ids:
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
        """Registra la salida de dinero y deja el egreso confirmado.

        Un gasto se registra como asiento contra la caja central; una devolución
        como pago de salida al cliente en la caja del cajero, aplicado al saldo
        a favor elegido.
        """
        for egreso in self:
            if egreso.state != "draft":
                raise UserError(_("Este egreso ya fue confirmado o anulado."))
            if egreso.tipo == "devolucion":
                egreso._confirmar_devolucion()
                continue
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
        """Deja el egreso anulado sin borrar nada.

        Un gasto se anula revirtiendo su asiento. Una devolución se anula
        desaplicándola del saldo a favor y cancelando el pago: así el crédito
        del cliente vuelve a quedar disponible.
        """
        for egreso in self:
            if egreso.state != "posted":
                raise UserError(_("Sólo se puede anular un egreso confirmado."))
            if egreso.tipo == "devolucion":
                egreso._anular_devolucion()
                continue
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

    def _confirmar_devolucion(self):
        """Pago de salida al cliente en la caja del cajero, aplicado al crédito.

        El pago se crea **sin sudo** a propósito: `cash_session` estampa el turno
        abierto del usuario al crear el payment, y ese vínculo es lo que hace que
        la devolución baje del arqueo ([[B.27]]). Si el cajero no tiene turno
        abierto, el propio candado de `cash_session` lo frena — que es lo
        correcto: no puede salir dinero de una caja que no está abierta.
        """
        self.ensure_one()
        diario = self._diario_de_devoluciones()
        if self.name == "/":
            self.name = (
                self.env["ir.sequence"]
                .with_company(self.company_id)
                .next_by_code("yaguven.egreso.caja")
                or "/"
            )
        pago = self.env["account.payment"].with_company(self.company_id).create({
            "payment_type": "outbound",
            "partner_type": "customer",
            "partner_id": self.cliente_id.id,
            "amount": self.amount,
            "date": self.date,
            "journal_id": diario.id,
            "payment_method_line_id": self._metodo_de_salida(diario).id,
            "memo": "%s - %s" % (self.name, self.concepto),
        })
        pago.action_post()
        credito = self.credito_line_id.sudo()
        linea_pago = pago.sudo().move_id.line_ids.filtered(
            lambda l: l.account_id == credito.account_id and l.debit > 0
        )
        if not linea_pago:
            raise UserError(
                _(
                    "El pago se registró pero no se pudo aplicar al saldo a favor: "
                    "la cuenta del cliente en el pago (%(pago)s) no coincide con la "
                    "del saldo elegido (%(credito)s).",
                    pago=", ".join(pago.sudo().move_id.line_ids.mapped("account_id.display_name")),
                    credito=credito.account_id.display_name,
                )
            )
        (linea_pago | credito).reconcile()
        self.write({"payment_id": pago.id, "move_id": pago.sudo().move_id.id,
                    "state": "posted"})
        self._avisar_en_el_historial(titulo=_("Devolución confirmada"),
                                     asiento=pago.sudo().move_id)
        self._informar_a_los_avisados(pago)

    def _anular_devolucion(self):
        """Desaplica la devolución y cancela el pago: el crédito vuelve a estar.

        El vínculo `move_id` se suelta ANTES de cancelar: al volver el pago a
        borrador Odoo rehace su asiento, y con la referencia puesta el `restrict`
        del campo lo frena («Another model is using the record you are trying to
        delete»). El número del asiento queda en el historial, que es donde hay
        que buscarlo después.
        """
        self.ensure_one()
        pago = self.payment_id.sudo()
        nombre_asiento = self.move_id.sudo().display_name or pago.display_name
        self.write({"move_id": False, "state": "cancel"})
        if pago.state in ("paid", "in_process"):
            pago.move_id.line_ids.remove_move_reconcile()
            pago.action_draft()
            pago.action_cancel()
        self._avisar_en_el_historial_texto(
            titulo=_("Devolución anulada"),
            detalle_asiento=nombre_asiento,
        )

    def _metodo_de_salida(self, diario):
        """Método de pago que saca el dinero de la caja en el acto.

        No se deja al default ([[B.7]]): hay que elegir el método cuya cuenta de
        pendientes ES la cuenta de la caja, porque es el único que mueve el
        efectivo al confirmar. Un método con cuenta de pendientes distinta deja
        el pago «en proceso» y el dinero seguiría figurando en la caja hasta la
        conciliación.
        """
        self.ensure_one()
        cuenta_caja = diario.sudo().default_account_id
        metodos = diario.sudo().outbound_payment_method_line_ids
        directo = metodos.filtered(lambda m: m.payment_account_id == cuenta_caja)
        if not directo:
            raise UserError(
                _(
                    "La caja «%(diario)s» no tiene un método de salida que descuente "
                    "el dinero en el acto.\n\nEn el diario, alguno de los métodos de "
                    "pago de salida tiene que tener como cuenta de pendientes la "
                    "propia cuenta de la caja (%(cuenta)s).",
                    diario=diario.display_name,
                    cuenta=cuenta_caja.display_name,
                )
            )
        return directo[0]

    def _diario_de_devoluciones(self):
        """Diario de caja por el que sale el dinero de la devolución."""
        self.ensure_one()
        diario = self.company_id.sudo().yaguven_devolucion_journal_id
        if not diario:
            raise UserError(
                _(
                    "Falta configurar el diario de las devoluciones de la compañía "
                    "«%(compania)s».\n\nEn Ajustes → Contabilidad → Egresos de caja "
                    "hay que elegir la caja por la que sale el dinero.",
                    compania=self.company_id.display_name,
                )
            )
        return diario

    def _informar_a_los_avisados(self, pago):
        """Avisa a quienes la compañía tenga configurados.

        Va como comentario (no como nota) y con `partner_ids` explícitos: es la
        única forma de que la notificación llegue de verdad ([[C.4]]), y con
        `notify_skip_followers` no se le manda a nadie más ([[C.9]]).
        """
        self.ensure_one()
        destinatarios = self.company_id.sudo().yaguven_egreso_caja_aviso_partner_ids
        if not destinatarios:
            return
        cuerpo = (
            "<p><strong>%s</strong> devolvió dinero de la caja.</p>"
            "<p>Cliente: %s<br/>Importe: %s<br/>Concepto: %s<br/>Pago: %s</p>"
        ) % (
            html_escape(self.env.user.display_name),
            html_escape(self.cliente_id.display_name),
            html_escape(formatLang(self.env, self.amount, currency_obj=self.currency_id)),
            html_escape(self.concepto or ""),
            html_escape(pago.sudo().display_name),
        )
        self.message_subscribe(partner_ids=destinatarios.ids)
        self.message_post(
            body=Markup(cuerpo),
            subject=_("Devolución de caja %(numero)s", numero=self.name),
            message_type="comment",
            subtype_xmlid="mail.mt_comment",
            partner_ids=destinatarios.ids,
            notify_skip_followers=True,
        )

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

    def _avisar_en_el_historial_texto(self, titulo, detalle_asiento):
        """Igual que `_avisar_en_el_historial`, con el asiento ya resuelto a texto.

        Hace falta cuando el asiento dejó de estar vinculado (una devolución
        anulada suelta `move_id` antes de cancelar el pago).
        """
        self.ensure_one()
        cuerpo = (
            "<p><strong>%s</strong></p><p>Asiento: %s<br/>Importe: %s</p>"
        ) % (
            html_escape(titulo),
            html_escape(detalle_asiento or ""),
            html_escape(formatLang(self.env, self.amount, currency_obj=self.currency_id)),
        )
        self.message_post(
            body=Markup(cuerpo),
            subject=titulo,
            message_type="comment",
            subtype_xmlid="mail.mt_note",
        )

    def _avisar_en_el_historial(self, titulo, asiento):
        self.ensure_one()
        # en una devolución no hay cuenta elegida: lo que importa es el cliente
        if self.tipo == "devolucion":
            detalle = _("Cliente: %(quien)s", quien=self.cliente_id.display_name)
        else:
            detalle = _("Cuenta debitada: %(cuenta)s", cuenta=self.account_id.display_name)
        cuerpo = (
            "<p><strong>%s</strong></p>"
            "<p>Asiento: %s<br/>"
            "%s<br/>"
            "Importe: %s</p>"
        ) % (
            html_escape(titulo),
            html_escape(asiento.display_name),
            html_escape(detalle),
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
