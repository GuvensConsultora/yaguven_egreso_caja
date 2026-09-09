{
    "name": "Egresos de caja",
    "summary": "Una pantalla simple para registrar salidas de la caja central",
    "description": """
Egresos de caja
===============

Una sola pantalla, para una sola persona: registrar que salió dinero de la caja
central y a qué cuenta se imputa.

Se cargan cinco datos — fecha, cuenta a debitar, importe, concepto y, si hace
falta, una foto del comprobante — y al confirmar el módulo arma el asiento:
**debita la cuenta elegida y acredita la caja central**.

Para que la pantalla siga siendo simple, el selector de cuentas muestra
únicamente las que contabilidad haya habilitado, no el plan entero. Esa lista
vive en una tabla del módulo: no se marca nada sobre el plan de cuentas, así la
desinstalación no deja rastros.

Un egreso confirmado no se borra: se **anula**, lo que revierte el asiento y deja
el registro y su historial a la vista.

Comprobante para firmar
-----------------------

Desde *Imprimir* sale un comprobante en PDF con original y duplicado en la misma
hoja: el original queda en la caja y el duplicado se lo lleva quien recibió el
dinero. Lleva el importe en números y en letras, el concepto, la cuenta imputada
y el renglón de firma con aclaración y documento.

Se puede imprimir antes de confirmar —el papel se firma al entregar la plata— y en
ese caso el propio PDF avisa que todavía no tiene asiento registrado.

Configuración
-------------

El diario y la cuenta de caja central son configuración de la compañía y **nacen
vacíos a propósito**: mientras no estén cargados, el módulo lo dice en vez de
elegir una cuenta por su cuenta.

Permisos
--------

Dos permisos, bajo el privilegio *Egresos de caja*:

* **Carga** — carga, confirma y anula. No puede borrar.
* **Consulta** — ve la pantalla y el historial, sin tocar nada.

Quien no tenga ninguno de los dos no ve la aplicación. Las cuentas habilitadas
las administra contabilidad, no quien carga.
""",
    "author": "Yagüven C.G.",
    "website": "https://yaguven.com",
    "category": "Accounting/Accounting",
    "version": "19.0.2.0.0",
    "license": "LGPL-3",
    "depends": ["account", "mail"],
    "data": [
        "security/egreso_caja_groups.xml",
        "security/ir.model.access.csv",
        "data/egreso_caja_sequence.xml",
        "views/egreso_caja_views.xml",
        "report/egreso_caja_templates.xml",
        "report/egreso_caja_report.xml",
        "views/egreso_caja_cuenta_views.xml",
        "views/res_config_settings_views.xml",
        "views/menus.xml",
    ],
    "installable": True,
    "application": True,
    "auto_install": False,
}
