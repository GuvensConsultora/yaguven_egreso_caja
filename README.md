# Egresos de caja

Módulo de Yagüven C.G. para Odoo 19.

Una pantalla para registrar que salió dinero de la caja central: se elige la
cuenta a debitar y el sistema acredita la caja central por el mismo importe.

## Qué hace

- **Confirmar** arma el asiento en el diario configurado (debe la cuenta elegida,
  haber la caja central), lo postea y numera el egreso como `EGR/2026/00001`.
- **Anular** revierte ese asiento y deja el egreso como anulado. Un egreso
  confirmado no se borra nunca.
- Cada movimiento queda registrado en el historial del egreso, con la cuenta y
  el importe.

## Devoluciones de dinero a clientes

La misma pantalla registra devoluciones. Se elige *Devolución a cliente*, el
cliente, y **cuál de sus saldos a favor** se le devuelve. La cuenta contable no
aparece: la resuelve el sistema.

Al confirmar se registra un pago de salida por la caja configurada, aplicado a
ese saldo a favor, y se avisa a quienes estén configurados en la compañía. El
pago queda vinculado al **turno de caja abierto** de quien lo registra, así que
baja del arqueo de ese turno.

**No se puede devolver sin saldo a favor.** Si el cliente devolvió mercadería,
primero va la nota de crédito; ese crédito es el que después se devuelve.

## Configuración

1. **Ajustes → Contabilidad → Egresos de caja**: elegir el *Diario de egresos de
   caja* y la *Caja central a acreditar*. Los dos nacen vacíos: sin esto cargado
   el módulo avisa qué falta en vez de asumir una cuenta.
2. En la misma pantalla, *Devoluciones de dinero a clientes*: elegir la **caja
   por la que sale el dinero** (la del cajero, no la caja central) y **a quiénes
   se les avisa** cada devolución. La caja necesita un método de pago de salida
   cuya cuenta de pendientes sea la propia cuenta de la caja; si no lo tiene, el
   módulo lo dice al confirmar.
3. **Egresos de Caja → Configuración → Cuentas habilitadas**: agregar las cuentas
   que van a aparecer en el selector. Mientras la lista esté vacía no se puede
   cargar ningún egreso. Cada cuenta admite una nota de *para qué se usa*, y se
   puede desactivar sin perder el historial.
4. **Ajustes → Usuarios**: dar *Egresos de caja → Carga* a quien registra, y
   *Consulta* a quien sólo mira. Sin ninguno de los dos, la aplicación no
   aparece.

## Verificar que quedó bien

- **Que el asiento sea el correcto:** confirmar un egreso de prueba y abrirlo con
  *Ver asiento*. Tiene que tener dos líneas: la cuenta elegida al debe y la caja
  central al haber, por el mismo importe.
- **Que la caja central baje:** Contabilidad → Libro mayor, filtrar por la cuenta
  de caja central. El egreso figura al haber con el número `EGR/…`.
- **Que la anulación no borre nada:** anular ese egreso de prueba. El registro
  queda como *Anulado*, con los dos asientos —el original y el de reversión— a la
  vista en el formulario.
- **Que el permiso funcione:** entrar con un usuario sin ninguno de los dos
  permisos. La aplicación *Egresos de Caja* no tiene que aparecer en la pantalla
  inicial.

## Alcance

No toca ningún modelo nativo salvo dos campos de configuración en la compañía.
Las cuentas habilitadas viven en una tabla propia del módulo, no como marca sobre
el plan de cuentas.
