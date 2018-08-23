# -*- coding: iso-8859-1 -*-
import string
import types
import logging
import unicodedata
from Comandos.ComandoFiscalInterface import ComandoFiscalInterface
from Drivers.FiscalPrinterDriver import PrinterException
from ComandoInterface import formatText

NUMBER = 999990


class HasarComandos(ComandoFiscalInterface):
    # el traductor puede ser: TraductorFiscal o TraductorReceipt
    # path al modulo de traductor que este comando necesita
    traductorModule = "Traductores.TraductorFiscal"

    DEFAULT_DRIVER = "Hasar"

    _savedPayments = None
    _currentDocument = None
    _currentDocumentType = None

    CMD_OPEN_FISCAL_RECEIPT = 0x40

    CMD_OPEN_CREDIT_NOTE = 0x80

    CMD_PRINT_TEXT_IN_FISCAL = 0x41
    CMD_PRINT_LINE_ITEM = 0x42
    CMD_PRINT_SUBTOTAL = 0x43
    CMD_ADD_PAYMENT = 0x44
    CMD_CLOSE_FISCAL_RECEIPT = 0x45
    CMD_DAILY_CLOSE = 0x39
    CMD_STATUS_REQUEST = 0x2a

    CMD_CLOSE_CREDIT_NOTE = 0x81

    CMD_CREDIT_NOTE_REFERENCE = 0x93
    CMD_PERCEPTIONS = 0x60

    CMD_SET_CUSTOMER_DATA = 0x62
    CMD_LAST_ITEM_DISCOUNT = 0x55
    CMD_GENERAL_DISCOUNT = 0x54

    CMD_OPEN_NON_FISCAL_RECEIPT = 0x48
    CMD_PRINT_NON_FISCAL_TEXT = 0x49
    CMD_CLOSE_NON_FISCAL_RECEIPT = 0x4a

    CMD_CANCEL_ANY_DOCUMENT = 0x98

    CMD_OPEN_DRAWER = 0x7b

    CMD_SET_HEADER_TRAILER = 0x5d

    # Documentos no fiscales homologados (remitos, recibos, etc.)
    CMD_OPEN_DNFH = 0x80
    CMD_PRINT_EMBARK_ITEM = 0x82
    CMD_PRINT_ACCOUNT_ITEM = 0x83
    CMD_PRINT_QUOTATION_ITEM = 0x84
    CMD_PRINT_DNFH_INFO = 0x85
    CMD_PRINT_RECEIPT_TEXT = 0x97
    CMD_CLOSE_DNFH = 0x81

    CMD_REPRINT = 0x99

    CURRENT_DOC_TICKET = 1
    CURRENT_DOC_BILL_TICKET = 2
    CURRENT_DOC_NON_FISCAL = 3
    CURRENT_DOC_CREDIT_BILL_TICKET = 4
    CURRENT_DOC_CREDIT_TICKET = 5
    CURRENT_DOC_DNFH = 6

    AVAILABLE_MODELS = ["615", "715v1", "715v2", "320"]

    textSizeDict = {
        "615": {'nonFiscalText': 40,
                'customerName': 30,
                'custAddressSize': 40,
                'paymentDescription': 30,
                'fiscalText': 20,
                'lineItem': 20,
                'lastItemDiscount': 20,
                'generalDiscount': 20,
                'embarkItem': 108,
                'receiptText': 106,
                },
        "320": {'nonFiscalText': 120,
                'customerName': 50,
                'custAddressSize': 50,
                'paymentDescription': 50,
                'fiscalText': 50,
                'lineItem': 50,
                'lastItemDiscount': 50,
                'generalDiscount': 50,
                'embarkItem': 108,
                'receiptText': 106,
                }
    }

    docTypeNames = {
        "DOC_TYPE_CUIT": "CUIT",
        "DOC_TYPE_LIBRETA_ENROLAMIENTO": 'L.E.',
        "DOC_TYPE_LIBRETA_CIVICA": 'L.C.',
        "DOC_TYPE_DNI": 'DNI',
        "DOC_TYPE_PASAPORTE": 'PASAP',
        "DOC_TYPE_CEDULA": 'CED',
        "DOC_TYPE_SIN_CALIFICADOR": 'S/C'
    }

    docTypes = {
        "CUIT": 'C',
        "LIBRETA_ENROLAMIENTO": '0',
        "LIBRETA_CIVICA": '1',
        "DNI": '2',
        "PASAPORTE": '3',
        "CEDULA": '4',
        "SIN_CALIFICADOR": ' ',
    }

    ivaTypes = {
        "RESPONSABLE_INSCRIPTO": 'I',
        "RESPONSABLE_NO_INSCRIPTO": 'N',
        "EXENTO": 'E',
        "NO_RESPONSABLE": 'A',
        "CONSUMIDOR_FINAL": 'C',
        "RESPONSABLE_NO_INSCRIPTO_BIENES_DE_USO": 'B',
        "RESPONSABLE_MONOTRIBUTO": 'M',
        "MONOTRIBUTISTA_SOCIAL": 'S',
        "PEQUENIO_CONTRIBUYENTE_EVENTUAL": 'V',
        "PEQUENIO_CONTRIBUYENTE_EVENTUAL_SOCIAL": 'W',
        "NO_CATEGORIZADO": 'T',
    }

    def _sendCommand(self, commandNumber, parameters=(), skipStatusErrors=False):
        try:
            commandString = "SEND|0x%x|%s|%s" % (commandNumber, skipStatusErrors and "T" or "F",
                                                 str(parameters))
            logging.getLogger().info("sendCommand: %s" % commandString)

            ret = self.conector.sendCommand(commandNumber, parameters, skipStatusErrors)
            logging.getLogger().info("reply: %s" % ret)
            return ret
        except PrinterException, e:
            logging.getLogger().error("PrinterException: %s" % str(e))
            raise ComandoException("Error de la impresora fiscal: %s.\nComando enviado: %s" % \
                                   (str(e), commandString))

    def openNonFiscalReceipt(self):
        status = self._sendCommand(self.CMD_OPEN_NON_FISCAL_RECEIPT, [])

        def checkStatusInComprobante(x):
            fiscalStatus = int(x, 16)
            return (fiscalStatus & (1 << 13)) == (1 << 13)

        if not checkStatusInComprobante(status[1]):
            # No tom� el comando, el status fiscal dice que no hay comprobante abierto, intento de nuevo
            status = self._sendCommand(self.CMD_OPEN_NON_FISCAL_RECEIPT, [])
            if not checkStatusInComprobante(status[1]):
                raise ComandoException("Error de la impresora fiscal, no acepta el comando de iniciar "
                                       "un ticket no fiscal")

        self._currentDocument = self.CURRENT_DOC_NON_FISCAL
        return status

    def _formatText(self, text, context):
        sizeDict = self.textSizeDict.get(self.model)
        if not sizeDict:
            sizeDict = self.textSizeDict["615"]
        return formatText(text)[:sizeDict.get(context, 20)]

    def printNonFiscalText(self, text):
        return self._sendCommand(self.CMD_PRINT_NON_FISCAL_TEXT, [self._formatText(text,
                                                                                   'nonFiscalText') or " ", "0"])

    ADDRESS_SIZE = 40

    def _setHeaderTrailer(self, line, text):
        if text:
            self._sendCommand(self.CMD_SET_HEADER_TRAILER, (str(line), text))

    def setHeader(self, header=None):
        "Establecer encabezados"
        if not header:
            header = []
        line = 3
        for text in (header + [chr(0x7f)] * 3)[:3]:  # Agrego chr(0x7f) (DEL) al final para limpiar las
            # l�neas no utilizadas
            self._setHeaderTrailer(line, text)
            line += 1

    def setTrailer(self, trailer=None):
        "Establecer pie"
        if not trailer:
            trailer = []
        line = 11
        for text in (trailer + [chr(0x7f)] * 9)[:9]:
            self._setHeaderTrailer(line, text)
            line += 1

    def _setCustomerData(self, name=" ", address=" ", doc=" ", docType=" ", ivaType="T"):
        # limpio el header y trailer:

        # self.setHeader()
        # self.setTrailer()
        doc = str(doc)
        doc = doc.replace("-", "").replace(".", "")
        if doc and docType != "3" and filter(lambda x: x not in string.digits, doc):
            # Si tiene letras se blanquea el DNI para evitar errores, excepto que sea
            # docType="3" (Pasaporte)
            doc, docType = " ", " "
        if not doc.strip():
            docType = " "

        if ivaType != "C" and (not doc or docType != "C"):
            raise ValidationError("Error, si el tipo de IVA del cliente NO es consumidor final, "
                                  "debe ingresar su n�mero de CUIT.")
        parameters = [self._formatText(name, 'customerName'),
                      doc or " ",
                      ivaType,  # Iva Comprador
                      docType or " ",  # Tipo de Doc.
                      ]
        if self.model in ["715v1", "715v2", "320"]:
            parameters.append(self._formatText(address, 'custAddressSize') or " ")  # Domicilio
        else:
            parameters.append(formatText(address) or " ")
        return self._sendCommand(self.CMD_SET_CUSTOMER_DATA, parameters)

    def openBillTicket(self, type, name, address, doc, docType, ivaType):
        self.cancelAnyDocument()
        self._setCustomerData(name, address, doc, docType, ivaType)
        if type == "A":
            type = "A"
        else:
            type = "B"
        self._currentDocument = self.CURRENT_DOC_BILL_TICKET
        self._savedPayments = []
        return self._sendCommand(self.CMD_OPEN_FISCAL_RECEIPT, [type, "T"])

    def openTicket(self, defaultLetter="B"):
        if self.model == "320":
            self._sendCommand(self.CMD_OPEN_FISCAL_RECEIPT, [defaultLetter, "T"])
        else:
            self._sendCommand(self.CMD_OPEN_FISCAL_RECEIPT, ["T", "T"])
        self._currentDocument = self.CURRENT_DOC_TICKET
        self._savedPayments = []

    ##    def openCreditTicket( self ):
    ##        self._sendCommand( self.CMD_OPEN_CREDIT_NOTE, [ "S", "T" ] )
    ##        self._currentDocument = self.CURRENT_DOC_CREDIT_TICKET
    ##        self._savedPayments = []
    ##  NO SE PUEDE

    def openDebitNoteTicket(self, type, name, address, doc, docType, ivaType):
        self.cancelAnyDocument()
        if doc:
            self._setCustomerData(name, address, doc, docType, ivaType)
        if type == "A":
            type = "D"
        else:
            type = "E"
        self._currentDocument = self.CURRENT_DOC_BILL_TICKET
        self._savedPayments = []
        return self._sendCommand(self.CMD_OPEN_FISCAL_RECEIPT, [type, "T"])

    def openBillCreditTicket(self, type, name, address, doc, docType, ivaType, reference="NC"):
        self.cancelAnyDocument()
        self._setCustomerData(name, address, doc, docType, ivaType)
        if type == "A":
            type = "R"
        else:
            type = "S"
        reference = str(reference)
        self._currentDocument = self.CURRENT_DOC_CREDIT_BILL_TICKET
        self._savedPayments = []
        self._sendCommand(self.CMD_CREDIT_NOTE_REFERENCE, ["1", reference])
        self._sendCommand(self.CMD_OPEN_CREDIT_NOTE, [type, "T", reference])

    def openRemit(self, name, address, doc, docType, ivaType, copies=1):
        self._setCustomerData(name, address, doc, docType, ivaType)
        self._currentDocument = self.CURRENT_DOC_DNFH
        self._savedPayments = []
        self._copies = copies
        return self._sendCommand(self.CMD_OPEN_DNFH, ["r", "T"])

    def openReceipt(self, name, address, doc, docType, ivaType, number, copies=1):
        self._setCustomerData(name, address, doc, docType, ivaType)
        self._currentDocument = self.CURRENT_DOC_DNFH
        self._savedPayments = []
        self._copies = copies
        return self._sendCommand(self.CMD_OPEN_DNFH, ["x", "T", number[:20]])

    def closeDocument(self):
        if self._currentDocument in (self.CURRENT_DOC_TICKET, self.CURRENT_DOC_BILL_TICKET):
            for desc, payment in self._savedPayments:
                self._sendCommand(self.CMD_ADD_PAYMENT, [self._formatText(desc, "paymentDescription"),
                                                         payment, "T", "1"])
            del self._savedPayments
            reply = self._sendCommand(self.CMD_CLOSE_FISCAL_RECEIPT)
            return reply[2]
        if self._currentDocument in (self.CURRENT_DOC_NON_FISCAL,):
            return self._sendCommand(self.CMD_CLOSE_NON_FISCAL_RECEIPT)
        if self._currentDocument in (self.CURRENT_DOC_CREDIT_BILL_TICKET, self.CURRENT_DOC_CREDIT_TICKET):
            reply = self._sendCommand(self.CMD_CLOSE_CREDIT_NOTE)
            return reply[2]
        if self._currentDocument in (self.CURRENT_DOC_DNFH,):
            reply = self._sendCommand(self.CMD_CLOSE_DNFH)
            # Reimprimir copias (si es necesario)
            for copy in range(self._copies - 1):
                self._sendCommand(self.CMD_REPRINT)
            return reply[2]
        raise NotImplementedError

    def cancelDocument(self):
        if not hasattr(self, "_currentDocument"):
            return
        if self._currentDocument in (self.CURRENT_DOC_TICKET, self.CURRENT_DOC_BILL_TICKET,
                                     self.CURRENT_DOC_CREDIT_BILL_TICKET, self.CURRENT_DOC_CREDIT_TICKET):
            try:
                status = self._sendCommand(self.CMD_ADD_PAYMENT, ["Cancelar", "0.00", 'C', "1"])
            except:
                self.cancelAnyDocument()
                status = []
            return status
        if self._currentDocument in (self.CURRENT_DOC_NON_FISCAL,):
            self.printNonFiscalText("CANCELADO")
            return self.closeDocument()
        if self._currentDocument in (self.CURRENT_DOC_DNFH,):
            self.cancelAnyDocument()
            status = []
            return status
        raise NotImplementedError

    def addItem(self, description, quantity, price, iva, itemNegative=False, discount=0, discountDescription='',
                discountNegative=True):
        if type(description) in types.StringTypes:
            description = [description]
        if itemNegative:
            sign = 'm'
        else:
            sign = 'M'
        quantityStr = str(float(quantity)).replace(',', '.')
        priceUnit = price
        priceUnitStr = str(priceUnit).replace(",", ".")
        ivaStr = str(float(iva)).replace(",", ".")
        for d in description[:-1]:
            self._sendCommand(self.CMD_PRINT_TEXT_IN_FISCAL, [self._formatText(d, 'fiscalText'), "0"])
        reply = self._sendCommand(self.CMD_PRINT_LINE_ITEM,
                                  [self._formatText(description[-1], 'lineItem'),
                                   quantityStr, priceUnitStr, ivaStr, sign, "0.0", "1", "T"])
        if discount:
            if discountNegative:
                sign = 'm'
            else:
                sign = 'M'
            discountStr = str(float(discount)).replace(",", ".")
            self._sendCommand(self.CMD_LAST_ITEM_DISCOUNT,
                              [self._formatText(discountDescription, 'discountDescription'), discountStr,
                               sign, "1", "T"])
        return reply

    def addPayment(self, description, payment):
        paymentStr = ("%.2f" % round(payment, 2)).replace(",", ".")
        self._savedPayments.append((description, paymentStr))

    def addPerception(self, description, price, iva='21.0', porcPerc=0):
        priceUnit = price
        priceUnitStr = str(priceUnit).replace(",", ".")

        if isinstance(iva, basestring):
            ivaStr = iva.replace(",", ".")
        else:
            ivaStr = str(float(iva)).replace(",", ".")

        reply = self._sendCommand(self.CMD_PERCEPTIONS, [ivaStr, self._formatText(description, 'perception'), priceUnitStr])
        return reply

    def addAdditional(self, description, amount, iva, negative=False):
        """Agrega un adicional a la FC.
            @param description  Descripci�n
            @param amount       Importe (sin iva en FC A, sino con IVA)
            @param iva          Porcentaje de Iva
            @param negative True->Descuento, False->Recargo"""

        if negative:
            if not description:
                description = "Descuento"
            sign = 'm'
        else:
            if not description:
                description = "Recargo"
            sign = 'M'
        priceUnit = amount
        priceUnitStr = str(priceUnit).replace(",", ".")
        reply = self._sendCommand(self.CMD_GENERAL_DISCOUNT,
                                  [self._formatText(description, 'generalDiscount'), priceUnitStr, sign, "1", "T"])
        return reply

    def addRemitItem(self, description, quantity):
        quantityStr = str(float(quantity)).replace(',', '.')
        return self._sendCommand(self.CMD_PRINT_EMBARK_ITEM,
                                 [self._formatText(description, 'embarkItem'), quantityStr, "1"])

    def addReceiptDetail(self, descriptions, amount):
        # Acumula el importe (no imprime)
        sign = 'M'
        quantityStr = str(float(1)).replace(',', '.')
        priceUnitStr = str(amount).replace(",", ".")
        ivaStr = str(float(0)).replace(",", ".")
        reply = self._sendCommand(self.CMD_PRINT_LINE_ITEM,
                                  ["Total",
                                   quantityStr, priceUnitStr, ivaStr, sign, "0.0", "1", "T"])
        # Imprimir textos
        for d in descriptions[:9]:  # hasta nueve lineas
            reply = self._sendCommand(self.CMD_PRINT_RECEIPT_TEXT,
                                      [self._formatText(d, 'receiptText')])
        return reply

    def openDrawer(self):
        if not self.model in ("320", "615"):
            self._sendCommand(self.CMD_OPEN_DRAWER, [])

    def dailyClose(self, type):
        reply = self._sendCommand(self.CMD_DAILY_CLOSE, [type])

        datos = [
            "status_impresora",
            "status_fiscal",
            "zeta_numero",
            "cant_doc_fiscales_cancelados",
            "cant_doc_nofiscales_homologados",
            "cant_doc_nofiscales",
            "cant_doc_fiscales",
            "RESERVADO_SIEMPRE_CERO",
            "ultimo_doc_b",
            "ultimo_doc_a",
            "monto_ventas_doc_fiscal",
            "monto_iva_doc_fiscal",
            "monto_imp_internos",
            "monto_percepciones",
            "monto_iva_no_inscripto",
            "ultima_nc_b",
            "ultima_nc_a",
            "monto_credito_nc",
            "monto_iva_nc",
            "monto_imp_internos_nc",
            "monto_percepciones_nc",
            "monto_iva_no_inscripto_nc",
            "ultimo_remito",
            "cant_nc_canceladas",
            "cant_doc_fiscales_bc_emitidos",
            "cant_doc_fiscales_a_emitidos",
            "cant_nc_bc_emitidos",
            "cant_nc_a_fiscales_a_emitidos"
        ]
        rta = {}
        for i, val in enumerate(datos):
            if len(reply) > i:
                rta[val] = reply[i]
            else:
                break

        return rta

    def getLastNumber(self, letter):
        reply = self._sendCommand(self.CMD_STATUS_REQUEST, [], True)
        if len(reply) < 3:
            # La respuesta no es v�lida. Vuelvo a hacer el pedido y
            # si hay alg�n error que se reporte como excepci�n
            reply = self._sendCommand(self.CMD_STATUS_REQUEST, [], False)
        if letter == "A":
            return int(reply[4])
        else:
            return int(reply[2])

    def getLastCreditNoteNumber(self, letter):
        reply = self._sendCommand(self.CMD_STATUS_REQUEST, [], True)
        if len(reply) < 3:
            # La respuesta no es v�lida. Vuelvo a hacer el pedido y
            # si hay alg�n error que se reporte como excepci�n
            reply = self._sendCommand(self.CMD_STATUS_REQUEST, [], False)
        if letter == "A":
            return int(reply[7])
        else:
            return int(reply[6])

    def getLastRemitNumber(self):
        reply = self._sendCommand(self.CMD_STATUS_REQUEST, [], True)
        if len(reply) < 3:
            # La respuesta no es v�lida. Vuelvo a hacer el pedido y si
            # hay alg�n error que se reporte como excepci�n
            reply = self._sendCommand(self.CMD_STATUS_REQUEST, [], False)
        return int(reply[8])

    def cancelAnyDocument(self):
        try:
            self._sendCommand(self.CMD_CANCEL_ANY_DOCUMENT)
        #            return True
        except:
            pass
        try:
            self._sendCommand(self.CMD_ADD_PAYMENT, ["Cancelar", "0.00", 'C', '1'])
            return True
        except:
            pass
        try:
            self._sendCommand(self.CMD_CLOSE_NON_FISCAL_RECEIPT)
            return True
        except:
            pass
        try:
            logging.getLogger().info("Cerrando comprobante con CLOSE")
            self._sendCommand(self.CMD_CLOSE_FISCAL_RECEIPT)
            return True
        except:
            pass
        return False

    def getWarnings(self):
        ret = []
        reply = self._sendCommand(self.CMD_STATUS_REQUEST, [], True)
        printerStatus = reply[0]
        x = int(printerStatus, 16)
        if ((1 << 4) & x) == (1 << 4):
            ret.append("Poco papel para la cinta de auditoria")
        if ((1 << 5) & x) == (1 << 5):
            ret.append("Poco papel para comprobantes o tickets")
        return ret

    def __del__(self):
        try:
            self.close()
        except:
            pass
