import collections
from datetime import datetime
import time

from backtrader import BrokerBase
from backtrader.utils.py3 import with_metaclass
from backtrader import Order, BuyOrder, SellOrder

from BackTraderQuik import QKStore


class MetaQKBroker(BrokerBase.__class__):
    def __init__(cls, name, bases, dct):
        super(MetaQKBroker, cls).__init__(name, bases, dct)  # Инициализируем класс брокера
        QKStore.BrokerCls = cls  # Регистрируем класс брокера в хранилище QUIK


class QKBroker(with_metaclass(MetaQKBroker, BrokerBase)):
    """Брокер QUIK"""
    # TODO Сделать обертку для поддержки множества счетов и брокеров
    # Обсуждение решения: https://community.backtrader.com/topic/1165/does-backtrader-support-multiple-brokers
    # Пример решения: https://github.com/JacobHanouna/backtrader/blob/ccxt_multi_broker/backtrader/brokers/ccxtmultibroker.py

    params = (
        ('use_positions', True),  # При запуске брокера подтягиваются текущие позиции с биржи
        ('Lots', True),  # Входящий остаток в лотах (задается брокером)
        ('ClientCode', ''),  # Код клиента
        ('FirmId', 'SPBFUT'),  # Фирма
        ('TradeAccountId', 'SPBFUT00PST'),  # Счет
        ('LimitKind', 0),  # День лимита
        ('CurrencyCode', 'SUR'),  # Валюта
        ('IsFutures', True),  # Фьючерсный счет
    )

    def __init__(self, **kwargs):
        super(QKBroker, self).__init__()
        self.store = QKStore(**kwargs)  # Хранилище QUIK
        self.notifs = collections.deque()  # Очередь уведомлений о заявках
        self.newTransId = 1  # Следующий внутренний номер транзакции заявки (В QUIK задается пользователем)
        self.tradeNums = dict()  # Список номеров сделок по тикеру для фильтрации дублей сделок
        self.startingcash = self.cash = 0  # Стартовые и текущие свободные средства по счету
        self.startingvalue = self.value = 0  # Стартовый и текущий баланс счета

    def start(self):
        super(QKBroker, self).start()
        self.startingcash = self.cash = self.getcash()  # Стартовые и текущие свободные средства по счету
        self.startingvalue = self.value = self.getvalue()  # Стартовый и текущий баланс счета
        if self.p.use_positions:  # Если нужно при запуске брокера получить текущие позиции на бирже
            self.store.GetPositions(self.p.ClientCode, self.p.FirmId, self.p.LimitKind, self.p.Lots, self.p.IsFutures)  # То получаем их
        self.store.qpProvider.OnConnected = self.store.OnConnected  # Соединение терминала с сервером QUIK
        self.store.qpProvider.OnDisconnected = self.store.OnDisconnected  # Отключение терминала от сервера QUIK
        self.store.qpProvider.OnTransReply = self.OnTransReply  # Ответ на транзакцию пользователя
        self.store.qpProvider.OnTrade = self.OnTrade  # Получение новой / изменение существующей сделки

    def getcash(self):
        """Свободные средства по счету"""
        if self.store.BrokerCls is not None:  # Если брокер есть в хранилище
            cash = self.store.GetMoneyLimits(self.p.ClientCode, self.p.FirmId, self.p.TradeAccountId, self.p.LimitKind, self.p.CurrencyCode, self.p.IsFutures)
            if cash is not None:  # Если свободные средства были получены
                self.cash = cash  # то запоминаем их
        return self.cash  # Возвращаем последние известные свободные средства

    def getvalue(self, datas=None):
        """Баланс счета"""
        if self.store.BrokerCls is not None:  # Если брокер есть в хранилище
            value = self.store.GetPositionsLimits(self.p.FirmId, self.p.TradeAccountId, self.p.IsFutures)
            if value is not None:  # Если баланс счета был получен
                self.value = value  # то запоминаем его
        return self.getcash() + self.value  # Возвращаем последний известный баланс счета

    def getposition(self, data, clone=True):
        """Позиция по тикеру
        Используется в strategy.py для закрытия (close) и ребалансировки (увеличения/уменьшения) позиции:
        - В процентах от портфеля (order_target_percent)
        - До нужного кол-ва (order_target_size)
        - До нужного объема (order_target_value)
        """
        pos = self.store.positions[data._dataname]  # Получаем позицию по тикеру или нулевую позицию если тикера в списке позиций нет
        if clone:  # Если нужно получить копию позиции
            pos = pos.clone()  # то создаем копию
        return pos  # Возвращаем позицию или ее копию

    def buy(self, owner, data, size, price=None, plimit=None, exectype=None, valid=None, tradeid=0, oco=None, trailamount=None, trailpercent=None, parent=None, transmit=True, **kwargs):
        """Заявка на покупку"""
        order = self.CreateOrder(owner, data, size, price, plimit, exectype, valid, oco, parent, transmit, True, ClientCode=self.p.ClientCode, TradeAccountId=self.p.TradeAccountId, **kwargs)
        self.notifs.append(order.clone())  # Удедомляем брокера об отправке новой заявки на рынок
        return order

    def sell(self, owner, data, size, price=None, plimit=None, exectype=None, valid=None, tradeid=0, oco=None, trailamount=None, trailpercent=None, parent=None, transmit=True, **kwargs):
        """Заявка на продажу"""
        order = self.CreateOrder(owner, data, size, price, plimit, exectype, valid, oco, parent, transmit, False, ClientCode=self.p.ClientCode, TradeAccountId=self.p.TradeAccountId, **kwargs)
        self.notifs.append(order.clone())  # Удедомляем брокера об отправке новой заявки на рынок
        return order

    def cancel(self, order):
        """Отмена заявки"""
        return self.store.CancelOrder(order)

    def get_notification(self):
        if not self.notifs:  # Если в списке уведомлений ничего нет
            return None  # то ничего и возвращаем, выходим, дальше не продолжаем

        return self.notifs.popleft()  # Удаляем и возвращаем крайний левый элемент списка уведомлений

    def next(self):
        self.notifs.append(None)  # Добавляем в список уведомлений пустой элемент

    def stop(self):
        super(QKBroker, self).stop()
        self.store.qpProvider.OnConnected = self.store.qpProvider.DefaultHandler  # Соединение терминала с сервером QUIK
        self.store.qpProvider.OnDisconnected = self.store.qpProvider.DefaultHandler  # Отключение терминала от сервера QUIK
        self.store.qpProvider.OnTransReply = self.store.qpProvider.DefaultHandler  # Ответ на транзакцию пользователя
        self.store.qpProvider.OnTrade = self.store.qpProvider.DefaultHandler  # Получение новой / изменение существующей сделки
        self.store.BrokerCls = None  # Удаляем класс брокера из хранилища

    def CreateOrder(self, owner, data, size, price=None, plimit=None, exectype=None, valid=None, oco=None, parent=None, transmit=True, IsBuy=True, **kwargs):
        """
        Создание заявки
        Привязка параметров счета и тикера
        Обработка связанных и родительской/дочерних заявок
        """
        order = BuyOrder(owner=owner, data=data, size=size, price=price, pricelimit=plimit, exectype=exectype, valid=valid, oco=oco, parent=parent, transmit=transmit) if IsBuy \
            else SellOrder(owner=owner, data=data, size=size, price=price, pricelimit=plimit, exectype=exectype, valid=valid, oco=oco, parent=parent, transmit=transmit)  # Заявка на покупку/продажу
        order.ref = self.newTransId  # Ставим номер транзакции в заявку
        self.newTransId += 1  # Увеличиваем номер транзакции для будущих заявок
        order.addcomminfo(self.getcommissioninfo(data))  # По тикеру выставляем комиссии в заявку. Нужно для исполнения заявки в BackTrader
        order.addinfo(**kwargs)  # Передаем в заявку все дополнительные свойства из брокера, в т.ч. ClientCode и TradeAccountId
        classCode, secCode = self.store.DataNameToClassSecCode(data._dataname)  # Из названия тикера получаем код площадки и тикера
        order.addinfo(ClassCode=classCode, SecCode=secCode)  # Код площадки ClassCode и тикера SecCode
        si = self.store.GetSecurityInfo(classCode, secCode)  # Получаем параметры тикера (min_price_step, scale)
        if si is None:  # Если тикер не найден
            print(f'Постановка заявки {order.ref} по тикеру {classCode}.{secCode} отменена. Тикер не найден')
            order.reject()  # то отменяем заявку
            return order  # Возвращаем отмененную заявку
        order.addinfo(Slippage=float(si['min_price_step']) * self.store.p.StopSteps)  # Размер проскальзывания в деньгах Slippage
        order.addinfo(Scale=int(si['scale']))  # Кол-во значащих цифр после запятой Scale
        if oco is not None:  # Если есть связанная заявка
            self.store.ocos[order.ref] = oco.ref  # то заносим в список связанных заявок
        if not transmit or parent is not None:  # Для родительской/дочерних заявок
            parentRef = getattr(order.parent, 'ref', order.ref)  # Номер транзакции родительской заявки или номер заявки, если родительской заявки нет
            if order.ref != parentRef and parentRef not in self.store.pcs:  # Если есть родительская заявка, но она не найдена в очереди родительских/дочерних заявок
                print(f'Постановка заявки {order.ref} по тикеру {classCode}.{secCode} отменена. Родительская заявка не найдена')
                order.reject()  # то отменяем заявку
                return order  # Возвращаем отмененную заявку
            pcs = self.store.pcs[parentRef]  # В очередь к родительской заявке
            pcs.append(order)  # добавляем заявку (родительскую или дочернюю)
        if transmit:  # Если обычная заявка или последняя дочерняя заявка
            if parent is None:  # Для обычных заявок
                return self.store.PlaceOrder(order)  # Отправляем заявку на рынок
            else:  # Если последняя заявка в цепочке родительской/дочерних заявок
                self.notifs.append(order.clone())  # Удедомляем брокера о создании новой заявки
                return self.store.PlaceOrder(order.parent)  # Отправляем родительскую заявку на рынок
        # Если не последняя заявка в цепочке родительской/дочерних заявок (transmit=False)
        return order  # то возвращаем созданную заявку со статусом Created. На рынок ее пока не ставим

    def OnTransReply(self, data):
        """Обработчик события ответа на транзакцию пользователя"""
        qkTransReply = data['data']  # Ответ на транзакцию
        transId = int(qkTransReply['trans_id'])  # Номер транзакции заявки
        if transId == 0:  # Заявки, выставленные не из автоторговли / только что (с нулевыми номерами транзакции)
            return  # не обрабатываем, пропускаем
        orderNum = int(qkTransReply['order_num'])  # Номер заявки на бирже
        try:  # Могут приходить другие заявки, не выставленные в автоторговле
            order: Order = self.store.orders[transId]  # Ищем заявку по номеру транзакции
        except KeyError:  # При ошибке
            print(f'Заявка {orderNum} на бирже с номером транзакции {transId} не найдена')
            return  # не обрабатываем, пропускаем
        self.store.orderNums[transId] = orderNum  # Сохраняем номер заявки на бирже
        # TODO Есть поле flags, но оно не документировано. Лучше вместо текстового результата транзакции разбирать по нему
        resultMsg = qkTransReply['result_msg']  # По результату исполнения транзакции (очень плохое решение)
        status = int(qkTransReply['status'])  # Статус транзакции
        if 'зарегистрирована' in resultMsg or status == 15:  # Если пришел ответ по новой заявке
            order.accept()  # Переводим заявку в статус Order.Accepted (регистрация новой заявки)
            self.notifs.append(order.clone())  # Уведомляем брокера о регистрации новой заявки
        elif 'снята' in resultMsg:  # Если пришел ответ по отмене существующей заявки
            try:  # TODO В BT очень редко при order.cancel() возникает ошибка:
                #    order.py, line 487, in cancel
                #    self.executed.dt = self.data.datetime[0]
                #    linebuffer.py, line 163, in __getitem__
                #    return self.array[self.idx + ago]
                #    IndexError: array index out of range
                order.cancel()  # Переводим заявку в статус Order.Canceled (отмена существующей заявки)
            except (KeyError, IndexError):  # При ошибке
                order.status = Order.Canceled  # все равно ставим статус заявки Order.Canceled
            self.notifs.append(order.clone())  # Уведомляем брокера об отмене существующей заявки
            self.store.OCOPCCheck(order)  # Проверяем связанные и родительскую/дочерние заявки (Canceled)
        elif status in (2, 4, 5, 10, 11, 12, 13, 14, 16):  # Транзакция не выполнена (ошибка заявки):
            # - Не найдена заявка для удаления
            # - Вы не можете снять данную заявку
            # - Превышен лимит отправки транзакций для данного логина
            if status == 4 and 'Не найдена заявка' in resultMsg or \
               status == 5 and 'не можете снять' in resultMsg or 'Превышен лимит' in resultMsg:
                return  # то заявку не отменяем, выходим, дальше не продолжаем
            try:  # TODO В BT очень редко при order.reject() возникает ошибка:
                #    order.py, line 480, in reject
                #    self.executed.dt = self.data.datetime[0]
                #    linebuffer.py, line 163, in __getitem__
                #    return self.array[self.idx + ago]
                #    IndexError: array index out of range
                order.reject()  # Переводим заявку в статус Order.Reject
            except (KeyError, IndexError):  # При ошибке
                order.status = Order.Rejected  # все равно ставим статус заявки Order.Rejected
            self.notifs.append(order.clone())  # Уведомляем брокера об ошибке заявки
            self.store.OCOPCCheck(order)  # Проверяем связанные и родительскую/дочерние заявки (Rejected)
        elif status == 6:  # Транзакция не прошла проверку лимитов сервера QUIK
            try:  # TODO В BT очень редко при order.margin() возникает ошибка:
                #    order.py, line 492, in margin
                #    self.executed.dt = self.data.datetime[0]
                #    linebuffer.py, line 163, in __getitem__
                #    return self.array[self.idx + ago]
                #    IndexError: array index out of range
                order.margin()  # Переводим заявку в статус Order.Margin
            except (KeyError, IndexError):  # При ошибке
                order.status = Order.Margin  # все равно ставим статус заявки Order.Margin
            self.notifs.append(order.clone())  # Уведомляем брокера о недостатке средств
            self.store.OCOPCCheck(order)  # Проверяем связанные и родительскую/дочерние заявки (Margin)

    def OnTrade(self, data):
        """Обработчик события получения новой / изменения существующей сделки.
        Выполняется до события изменения существующей заявки. Нужен для определения цены исполнения заявок.
        """
        qkTrade = data['data']  # Сделка в QUIK
        orderNum = int(qkTrade['order_num'])  # Номер заявки на бирже
        jsonOrder = self.store.qpProvider.GetOrderByNumber(orderNum)['data']  # По номеру заявки в сделке пробуем получить заявку с биржи
        if isinstance(jsonOrder, int):  # Если заявка не найдена, то в ответ получаем целое число номера заявки. Возможно заявка есть, но она не успела прийти к брокеру
            print(f'Заявка с номером {orderNum} не найдена на бирже с 1-ой попытки. Через 3 с будет 2-ая попытка')
            time.sleep(3)  # Ждем 3 секунды, пока заявка не придет к брокеру
            jsonOrder = self.store.qpProvider.GetOrderByNumber(orderNum)['data']  # Снова пробуем получить заявку с биржи по ее номеру
            if isinstance(jsonOrder, int):  # Если заявка так и не была найдена
                print(f'Заявка с номером {orderNum} не найдена на бирже со 2-ой попытки')
                return  # то выходим, дальше не продолжаем
        transId = int(jsonOrder['trans_id'])  # Получаем номер транзакции из заявки с биржи
        if transId == 0:  # Заявки, выставленные не из автоторговли / только что (с нулевыми номерами транзакции)
            return  # не обрабатываем, пропускаем
        self.store.orderNums[transId] = orderNum  # Сохраняем номер заявки на бирже (может быть переход от стоп заявки к лимитной с изменением номера на бирже)
        try:  # Бывает, что трейдеры совмещают авто и ручную торговлю. Это делать нельзя, но кто это будет слушать?
            order: Order = self.store.orders[transId]  # Ищем заявку по номеру транзакции
        except KeyError:  # Если пришла заявка из ручной торговли, то заявки по номеру транзакции в автоторговле не будет, получим ошибку
            print(f'Заявка с номером {orderNum} и номером транзакции {transId} была выставлена не из торговой системы')
            return  # выходим, дальше не продолжаем
        classCode = qkTrade['class_code']  # Код площадки
        secCode = qkTrade['sec_code']  # Код тикера
        dataname = self.store.ClassSecCodeToDataName(classCode, secCode)  # Получаем название тикера по коду площадки и коду тикера
        tradeNum = int(qkTrade['trade_num'])  # Номер сделки (дублируется 3 раза)
        if dataname not in self.tradeNums.keys():  # Если это первая сделка по тикеру
            self.tradeNums[dataname] = []  # то ставим пустой список сделок
        elif tradeNum in self.tradeNums[dataname]:  # Если номер сделки есть в списке (фильтр для дублей)
            return  # то выходим, дальше не продолжаем
        self.tradeNums[dataname].append(tradeNum)  # Запоминаем номер сделки по тикеру, чтобы в будущем ее не обрабатывать (фильтр для дублей)
        size = int(qkTrade['qty'])  # Абсолютное кол-во
        if self.p.Lots:  # Если входящий остаток в лотах
            size = self.store.LotsToSize(classCode, secCode, size)  # то переводим кол-во из лотов в штуки
        if qkTrade['flags'] & 0b100 == 0b100:  # Если сделка на продажу (бит 2)
            size *= -1  # то кол-во ставим отрицательным
        price = self.store.QKToBTPrice(classCode, secCode, float(qkTrade['price']))  # Переводим цену исполнения за лот в цену исполнения за штуку
        try:  # TODO Очень редко возникает ошибка:
            #    linebuffer.py, line 163, in __getitem__
            #    return self.array[self.idx + ago]
            #    IndexError: array index out of range
            dt = order.data.datetime[0]  # Дата и время исполнения заявки. Последняя известная
        except (KeyError, IndexError):  # При ошибке
            dt = datetime.now(QKStore.MarketTimeZone)  # Берем текущее время на рынке из локального
        pos = self.getposition(order.data, clone=False)  # Получаем позицию по тикеру или нулевую позицию если тикера в списке позиций нет
        psize, pprice, opened, closed = pos.update(size, price)  # Обновляем размер/цену позиции на размер/цену сделки
        order.execute(dt, size, price, closed, 0, 0, opened, 0, 0, 0, 0, psize, pprice)  # Исполняем заявку в BackTrader
        if order.executed.remsize:  # Если заявка исполнена частично (осталось что-то к исполнению)
            if order.status != order.Partial:  # Если заявка переходит в статус частичного исполнения (может исполняться несколькими частями)
                order.partial()  # Переводим заявку в статус Order.Partial
                self.notifs.append(order.clone())  # Уведомляем брокера о частичном исполнении заявки
        else:  # Если заявка исполнена полностью (ничего нет к исполнению)
            order.completed()  # Переводим заявку в статус Order.Completed
            self.notifs.append(order.clone())  # Уведомляем брокера о полном исполнении заявки
            # Снимаем oco-заявку только после полного исполнения заявки
            # Если нужно снять oco-заявку на частичном исполнении, то прописываем это правило в ТС
            self.store.OCOPCCheck(order)  # Проверяем связанные и родительскую/дочерние заявки (Completed)
