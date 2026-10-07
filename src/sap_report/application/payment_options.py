PAYMENT_ACCOUNT_OPTIONS = [
    "Caja Tda",
    "Tarjetas Visanet",
    "Tarjetas Mercadopago",
    "Tarjetas MCM",
    "Tarjetas Expressnet",
    "Pago Izipay",
    "Tarjetas Diners",
    "Tarjetas Estilos",
    "Efectivo Activa",
    "Deposito BCP",
    "Deposito Scotiabank",
    "Deposito Interbank",
    "Deposito BBVA",
    "Tarjetas Openpay",
]


# Un tipo de pago puede corresponder a mas de una cuenta en SAP. Caso visto el
# 2026-10-06: la orden FE5P08C454YD cae en TUTATI como "PayCash - Mercado Pago"
# y la regla de MySQL la agrupa en "Tarjetas Mercadopago", pero en SAP su cuenta
# (10310024) se llama "PayCash Boton Web". Sin esta equivalencia el cuadre las
# reportaba como faltantes en SAP cuando en realidad estaban.
PAYMENT_ACCOUNT_SAP_ALIASES: dict[str, list[str]] = {
    "Tarjetas Mercadopago": ["Tarjetas Mercadopago", "PayCash Boton Web"],
}


def cuentas_sap(account_name: str) -> list[str]:
    """Nombres de cuenta de SAP que corresponden a un tipo de pago."""
    return PAYMENT_ACCOUNT_SAP_ALIASES.get(account_name, [account_name])
