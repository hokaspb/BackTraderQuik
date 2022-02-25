from datetime import datetime, time
import backtrader as bt
from BackTraderQuik.QKStore import QKStore  # Хранилище QUIK
# from BackTraderQuik.QKBroker import QKBroker  # Брокер QUIK для вызвова напрямую (не рекомендуется)


class LiveTradingEvents(bt.Strategy):
    """
    Получение и отображение событий в QUIK:
    - Изменение статуса приходящих баров (DELAYED / CONNECTED / DISCONNECTED / LIVE)
    - Получение нового бара
    - Изменение статуса заявок
    - Изменение статуса позиций
    """
    def log(self, txt, dt=None):
        """Вывод строки с датой на консоль"""
        dt = bt.num2date(self.datas[0].datetime[0]) if dt is None else dt  # Заданная дата или дата текущего бара
        print(f'{dt.strftime("%d.%m.%Y %H:%M")}, {txt}')  # Выводим дату и время с заданным текстом на консоль

    def __init__(self):
        """Инициализация торговой системы"""
        self.isLive = False  # Сначала будут приходить исторические данные, затем перейдем в режим реальной торговли

    def next(self):
        """Получение следующего исторического/нового бара"""
        for data in self.datas:  # Пробегаемся по всем запрошенным барам
            self.log(f'{data.p.dataname} Open={data.open[0]:.2f}, High={data.high[0]:.2f}, Low={data.low[0]:.2f}, Close={data.close[0]:.2f}, Volume={data.volume[0]:.0f}')
        if self.isLive:  # Если в режиме реальной торговли
            self.log(f'Свободные средства: {self.broker.getcash()}, Баланс: {self.broker.getvalue()}')

    def notify_data(self, data, status, *args, **kwargs):
        """Изменение статуса приходящих баров"""
        dataStatus = data._getstatusname(status)  # Получаем статус (только при LiveBars=True)
        print(dataStatus)  # Не можем вывести в лог, т.к. первый статус DELAYED получаем до первого бара (и его даты)
        self.isLive = dataStatus == 'LIVE'  # Режим реальной торговли

    def notify_order(self, order):
        """Изменение статуса заявки"""
        if order.status in (bt.Order.Created, bt.Order.Submitted, bt.Order.Accepted):  # Если заявка создана, отправлена брокеру, принята брокером (не исполнена)
            self.log(f'Alive Status: {order.getstatusname()}. TransId={order.ref}')
        elif order.status in (bt.Order.Canceled, bt.Order.Margin, bt.Order.Rejected, bt.Order.Expired):  # Если заявка отменена, нет средств, заявка отклонена брокером, снята по времени (снята)
            self.log(f'Cancel Status: {order.getstatusname()}. TransId={order.ref}')
        elif order.status == bt.Order.Partial:  # Если заявка частично исполнена
            self.log(f'Part Status: {order.getstatusname()}. TransId={order.ref}')
        elif order.status == bt.Order.Completed:  # Если заявка полностью исполнена
            if order.isbuy():  # Заявка на покупку
                self.log(f'Bought @{order.executed.price:.2f}, Cost={order.executed.value:.2f}, Comm={order.executed.comm:.2f}')
            elif order.issell():  # Заявка на продажу
                self.log(f'Sold @{order.executed.price:.2f}, Cost={order.executed.value:.2f}, Comm={order.executed.comm:.2f}')

    def notify_trade(self, trade):
        """Изменение статуса позиции"""
        if trade.isclosed:  # Если позиция закрыта
            self.log(f'Trade Profit, Gross={trade.pnl:.2f}, NET={trade.pnlcomm:.2f}')


if __name__ == '__main__':  # Точка входа при запуске этого скрипта
    cerebro = bt.Cerebro()  # Инициируем "движок" BackTrader

    clientCode = '<Ваш код клиента>'  # Код клиента (присваивается брокером)
    firmId = '<Код фирмы>'  # Код фирмы (присваивается брокером)
    # symbol = 'TQBR.GAZP'
    symbol = 'SPBFUT.SiH2'

    cerebro.addstrategy(LiveTradingEvents)  # Добавляем торговую систему
    # broker = QKBroker(Host='<Ваш IP адрес>')  # Можно вызывать данные напрямую (не рекомендуется)
    store = QKStore()  # Хранилище QUIK (QUIK на локальном компьютере)
    # store = QKStore(Host='<Ваш IP адрес>')  # Хранилище QUIK (К QUIK на удаленном компьютере обращаемся по IP или названию)
    broker = store.getbroker(use_positions=False)  # Брокер со счетом по умолчанию (срочный рынок РФ)
    # broker = store.getbroker(use_positions=False, ClientCode=clientCode, FirmId=firmId, TradeAccountId='L01-00000F00', LimitKind=2, CurrencyCode='SUR', IsFutures=False)  # Брокер со счетом фондового рынка РФ
    cerebro.setbroker(broker)  # Устанавливаем брокера
    data = store.getdata(dataname=symbol, timeframe=bt.TimeFrame.Minutes, compression=1,
                         fromdate=datetime(2022, 2, 16), sessionstart=time(7, 0), LiveBars=True)  # Исторические и новые минутные бары за все время
    cerebro.adddata(data)  # Добавляем данные
    cerebro.addsizer(bt.sizers.FixedSize, stake=1000)  # Кол-во акций для покупки/продажи
    cerebro.run()  # Запуск торговой системы
