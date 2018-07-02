# encoding=utf8
from fcoin import Fcoin
import time
import datetime
import sys

fcoin = Fcoin()

# 订单取消时间
timeout = 300

# 交易对
symbol = "ltcusdt"

# 设置appkey/appsecret
fcoin.auth('appkey', 'appsecret')

# 格式
tradeIDs = []

#ltcusdt信息
ltcusdt_ticket = {
    "cur_price": 0,
    "cur_price_count": 0,
    "buy_price": 0,
    "buy_price_count": 0,
    "sale_price": 0,
    "sale_price_count": 0,
    # 默认为安全值
    "real_sale_price": 1000,
}

# 用户币账户余额
balance_ltc = 0
balance_ft = 0
balance_usdt = 0

# 价格安全阀值
min_trade_price_ltcusdt = 94
max_trade_price_ltcusdt = 108

# 买一卖一量安全阀值
sale_trade_count_ltcusdt = 50
buy_trade_count_ltcusdt = 150


# 单笔买卖比例
trade_buy_rate = 0.25
trade_sale_rate = 0.25

# 单笔买卖最大值
max_trade_count_usdt = 1000
max_trade_count_ltc = 10

# 最大允许买卖单差价
max_buy_sale_price_distance = 0.02

# smart价格调控参数(买卖智能调整阀值)
smart_buy_price_count = 1200
smart_sale_price_count = 150

# 全局控制是否交易
do_trade = False

# 检测取消订单频率
checkTradeIDCount = 10

# 流程：
# 查看所有的订单、查看是否有超时订单，循环看账户余额判断是否能进行买卖
# 当有订单时间超过90s执行撤销操作
# 查询用户账单余额
# 判断有ltc则进行卖出操作，有usdt则执行买入操作
# 获取现价ltcusdt的买1价设置为买单或卖单的价格
# 挂单操作

# submitted	已提交
# partial_filled	部分成交
# partial_canceled	部分成交已撤销
# filled	完全成交
# canceled	已撤销
# pending_cancel	撤销已提交


# 查看历史未完成订单
def init_trade_ids(fcoin, trade_ids):
    try:
        del trade_ids[:]
        result = fcoin.list_orders(symbol=symbol, states="submitted")
        submitted_len = len(result['data'])
        for i in range(0, submitted_len):
            trade_ids.append({"id": result['data'][i]['id'], "time": result['data'][i]['created_at']/1000})
        result = fcoin.list_orders(symbol=symbol, states="partial_filled")
        submitted_len = len(result['data'])
        for i in range(0, submitted_len):
            trade_ids.append({"id": result['data'][i]['id'], "time": result['data'][i]['created_at'] / 1000})
    except Exception, ex:
        print 'init_trade_ids exception!!'
        time.sleep(1)


# 取消订单
def check_trade(fcoin, trade_ids):
    try:
        now_time = time.time()
        for i in range(0, len(trade_ids)):
            if (now_time - trade_ids[i]['time']) > timeout:
                print "取消订单id:", trade_ids[i]['id']
                fcoin.cancel_order(trade_ids[i]['id'])
    except Exception, ex:
        print 'check_trade exception!!'
        time.sleep(1)


# 读取用户账单数据
def init_balance(fcoin):
    try:
        global balance_ltc, balance_ft, balance_usdt
        result = fcoin.get_balance()
        if result.has_key('data'):
            for i in range(len(result['data'])):
                if result['data'][i]['currency'] == 'ltc':
                    balance_ltc = round(float(result['data'][i]['available']), 6) - 0.000001
                elif result['data'][i]['currency'] == 'ft':
                    balance_ft = round(float(result['data'][i]['available']), 6) - 0.000001
                elif result['data'][i]['currency'] == 'usdt':
                    balance_usdt = round(float(result['data'][i]['available']), 6) - 0.000001
        else:
            balance_ltc = 0
            balance_ft = 0
            balance_usdt = 0
    except Exception, ex:
        print 'init_balance exception!!'
        time.sleep(1)


# 分析交易数据
def analyse_ticket(fcoin):
    global ltcusdt_ticket, do_trade
    try:
        result = fcoin.get_market_ticker(symbol)
        ltcusdt_ticket = {
            "cur_price": result['data']['ticker'][0],
            "cur_price_count": result['data']['ticker'][1],
            "buy_price": result['data']['ticker'][2],
            "buy_price_count": result['data']['ticker'][3],
            "sale_price": result['data']['ticker'][4],
            "sale_price_count": result['data']['ticker'][5],
        }

        # 风险处理 （判断差价是否过大）
        if (ltcusdt_ticket['buy_price'] - ltcusdt_ticket['sale_price']) > max_buy_sale_price_distance:
            do_trade = False
            return

        # 如果买量过高、加价0.01买
        if ltcusdt_ticket['buy_price_count'] > smart_buy_price_count:
            ltcusdt_ticket['buy_price'] += 0.01
        # 如果卖量过少、加价0.01卖
        if ltcusdt_ticket['sale_price_count'] < smart_sale_price_count:
            ltcusdt_ticket['sale_price'] += 0.01

        if (ltcusdt_ticket['buy_price'] - ltcusdt_ticket['sale_price']) >= 0.01:
            do_trade = False
            return

        # 调整卖价
        ltcusdt_ticket['real_sale_price'] = ltcusdt_ticket['sale_price'] - 0.00

        if ltcusdt_ticket['real_sale_price'] < ltcusdt_ticket['buy_price']:
            ltcusdt_ticket['real_sale_price'] = ltcusdt_ticket['buy_price']

        # 不可超过价格安全阀值  暂时高于100不买、低于96不卖
        # 买一量和卖一量大小限制
        if ltcusdt_ticket['buy_price'] > max_trade_price_ltcusdt or ltcusdt_ticket['real_sale_price'] < min_trade_price_ltcusdt \
                or ltcusdt_ticket['buy_price_count'] < buy_trade_count_ltcusdt or ltcusdt_ticket['sale_price_count'] < sale_trade_count_ltcusdt:
            do_trade = False
        else:
            do_trade = True
    except Exception, ex:
        print 'analyse_ticket exception!!'
        do_trade = False
        time.sleep(1)


def do_fcoin_trade(fcoin):
    try:
        global balance_ltc, balance_ft, balance_usdt, ltcusdt_ticket

        if do_trade:
            buy_count = 0
            buy_trade_count_usdt = balance_usdt * trade_buy_rate # 按20%投注
            sale_count = balance_ltc * trade_sale_rate # 按20%投注
            # do buy
            if balance_usdt > 1 and ltcusdt_ticket['buy_price'] > 0:
                if buy_trade_count_usdt > max_trade_count_usdt:
                    buy_trade_count_usdt = max_trade_count_usdt
                buy_count = round(float(buy_trade_count_usdt / ltcusdt_ticket['buy_price']) - 0.0001, 4)
                print "[BUY] do buy trade! real buy price is:", ltcusdt_ticket['buy_price'], \
                    " buy count is:", buy_count
            # do sale
            if balance_ltc > 0.1 and ltcusdt_ticket['real_sale_price'] > 0:
                if sale_count > max_trade_count_ltc:
                    sale_count = max_trade_count_ltc
                sale_count = round(sale_count - 0.0001, 4)
                print "[SELL] do sell trade! real sale price is:", ltcusdt_ticket['real_sale_price'], \
                    " sale count is:", sale_count
        else:
            print 'not do fcoin trade!!!!!!'
            time.sleep(1)
    except Exception, ex:
        print 'do_fcoin_trade exception!!'
        time.sleep(1)

while 1:
    sys.stdout.flush()
    time_start = time.time()
    if checkTradeIDCount >= 10:
        init_trade_ids(fcoin, tradeIDs)
        check_trade(fcoin, tradeIDs)
        checkTradeIDCount = 0
        time.sleep(1)
    analyse_ticket(fcoin)
    checkTradeIDCount += 1
    if do_trade:
        init_balance(fcoin)
        print "user balance is usdt:", balance_usdt, " ltc:", balance_ltc, " ft:", balance_ft
        do_fcoin_trade(fcoin)
        time.sleep(2)
    else:
        time.sleep(2)
    print ""













