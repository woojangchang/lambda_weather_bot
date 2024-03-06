from selenium import webdriver
from tempfile import mkdtemp
import pandas as pd
import numpy as np
from bs4 import BeautifulSoup
import datetime
import time
import json
import os
import requests

TOKEN = os.environ['TOKEN']
CHAT_ID = os.environ['CHAT_ID']
TELEGRAM_URL = "https://api.telegram.org/bot{}/sendMessage".format(TOKEN)


def handler(event=None, context=None):
    options = webdriver.ChromeOptions()
    service = webdriver.ChromeService("/opt/chromedriver")

    options.binary_location = '/opt/chrome/chrome'
    options.add_argument("--headless=new")
    options.add_argument('--no-sandbox')
    options.add_argument("--disable-gpu")
    options.add_argument("--window-size=1280x1696")
    options.add_argument("--single-process")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--disable-dev-tools")
    options.add_argument("--no-zygote")
    options.add_argument(f"--user-data-dir={mkdtemp()}")
    options.add_argument(f"--data-path={mkdtemp()}")
    options.add_argument(f"--disk-cache-dir={mkdtemp()}")
    options.add_argument("--remote-debugging-port=9222")
    
    
    d_today = datetime.datetime.now() + datetime.timedelta(hours=9)
    # d_today = d_today.strftime('%Y-%m-%d')
    
    result = pd.DataFrame()
    forecast_kor = {'KMA': '기상청', 'ACCUWEATHER': '아큐웨더',
                    'TWC': '웨더채널', 'WEATHERNEWS': '웨더뉴스'}
    
    for forecast in forecast_kor.keys():
        driver = webdriver.Chrome(options=options, service=service)
    
        url = 'https://weather.naver.com/today/?cpName={}'.format(forecast)
        driver.get(url)
    
        time.sleep(1)
    
        html = driver.page_source
        soup = BeautifulSoup(html, 'lxml')
    
        weather_data = soup.find_all(attrs={'class': 'top'})
    
        ymdt = [a['data-ymdt'] for a in weather_data]
        temp = [int(a['data-tmpr']) for a in weather_data]
    
        weather_data = soup.find(attrs={'class': 'weather_table_wrap'})
    
        rain_prob = []
        rain_amount = []
        for t in ymdt:
            rain = weather_data.find_all(attrs={'data-ymdt': t})
            prob = rain[1].text.strip()
    
            amount = rain[2].text.strip()
            if '~1' == amount:
                amount = '0.5'
    
            rain_prob.append(prob)
            rain_amount.append(amount)
    
        ymdt_col = [f'{t[:4]}년 {t[4:6]}월 {t[6:8]}일 {t[8:]}시' for t in ymdt]
    
        tmp = pd.DataFrame([temp, rain_prob, rain_amount], columns=ymdt_col, index=[
                            [forecast_kor[forecast] for _ in range(3)], ['기온', '강수확률', '강수량']])
        tmp.index.names = ['제공사', '날씨']
        result = pd.concat([result, tmp], axis=0)
        driver.close()
    
    d_today_last = f'{d_today.year}년 {d_today.month:02d}월 {d_today.day:02d}일 23시'
    time_today = [t for t in result.columns if t <= d_today_last]
    
    r = result[time_today].copy().astype(str)
    
    for forecast in forecast_kor.values():
        r.loc[(forecast, ['기온']), ['최저']] = r.loc[(forecast, ['기온']),
                                                    :d_today_last].replace('nan', np.nan).dropna(axis=1).astype(int).min(axis=1).astype(str)
        r.loc[(forecast, ['기온']), ['최고']] = r.loc[(forecast, ['기온']),
                                                    :d_today_last].replace('nan', np.nan).dropna(axis=1).astype(int).max(axis=1).astype(str)
        r.loc[(forecast, ['강수확률', '강수량']), '최저'] = '-'
        r.loc[(forecast, ['강수확률', '강수량']), '최고'] = '-'
    
    index = [f'{d_today.year}년', f'{d_today.month}월 {d_today.day}일']
    r.columns = [t[-3:] for t in r.columns]
    r.index.names = index
    
    order_where = ['기상청', '아큐웨더', '웨더채널', '웨더뉴스']
    order_index = ['기온', '강수확률', '강수량']
    
    
    
    for i in range(0, len(r.columns), 3):
        tmp = r.iloc[:, i:i+3].reset_index()
        tmp[index[0]] = pd.Categorical(tmp[index[0]], categories=order_where, ordered=True)
        tmp[index[1]] = pd.Categorical(tmp[index[1]], categories=order_index, ordered=True)
        tmp = tmp.sort_values(by=[index[1], index[0]])
        
        if i == 0:
            msg = '<b>날씨 알림</b>'
        else:
            msg = ''
        msg += f'<pre>{tmp.to_markdown(index=None, tablefmt="grid")}</pre>'
    
        try:
            payload = {
                "text": msg,
                "chat_id": CHAT_ID,
                "parse_mode":"HTML"
            }
            response = json.loads(requests.post(TELEGRAM_URL, payload).text)
            if not response['ok']:
                raise Exception(response['description'])
        except Exception as e:
            raise e
        
    return {"status":"OK"}
    # return r.to_json(force_ascii=False)
