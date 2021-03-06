# -*- coding: utf-8 -*-

import re
import os
import requests
import subprocess
import logging
import json
import pandas as pd
import numpy as np
import datetime as dt
import six
import traceback
import time
import argparse
import pprint
from wordsub import english_word_sub

logger = logging.getLogger('hr.chatbot.utils')

try:
    from google.cloud import translate
except ImportError:
    logger.error("Can't import google translate")

OPENWEATHERAPPID = os.environ.get('OPENWEATHERAPPID')
CITY_LIST_FILE = os.environ.get('CITY_LIST_FILE')
GCLOUD_API_KEY = os.environ.get('GCLOUD_API_KEY')
PUNCTUATORS = re.compile(r"""[.|?|!]+$""")

cities = None

CHATBOT_LANGUAGE_DICT = {
    'am': ['am-ET'],
    'ar': ['ar-IL', 'ar-JO', 'ar-AE', 'ar-BH', 'ar-DZ', 'ar-SA', 'ar-IQ', 'ar-KW', 'ar-MA', 'ar-TN', 'ar-OM', 'ar-PS', 'ar-QA', 'ar-LB', 'ar-EG'],
    'zh-CN': ['cmn-Hans-CN', 'cmn-Hans-HK'],
    'zh-TW': ['cmn-Hant-TW', 'yue-Hant-HK'],
    'nl': ['nl-NL'],
    'en': ['en-AU', 'en-CA', 'en-GH', 'en-GB', 'en-IN', 'en-IE', 'en-KE', 'en-NZ', 'en-NG', 'en-PH', 'en-ZA', 'en-TZ', 'en-US'],
    'fr': ['fr-CA', 'fr-FR'],
    'de': ['de-DE'],
    'hi': ['hi-IN'],
    'it': ['it-IT'],
    'ja': ['ja-JP'],
    'ko': ['ko-KR'],
    'lt': ['lt-LT'],
    'pt': ['pt-BR', 'pt-PT'],
    'ru': ['ru-RU'],
    'es': ['es-AR', 'es-BO', 'es-CL', 'es-CO', 'es-CR', 'es-EC', 'es-SV', 'es-ES', 'es-US', 'es-GT', 'es-HN', 'es-MX', 'es-NI', 'es-PA', 'es-PY', 'es-PE', 'es-PR', 'es-DO', 'es-UY', 'es-VE'],
    'tr': ['tr-TR'],
}

def query_city_info(name):
    global cities
    if cities is None:
        if CITY_LIST_FILE:
            with open(CITY_LIST_FILE) as f:
                cities = json.load(f)
    for city in cities:
        if name.title() in city['name']:
            return city

def str_cleanup(text):
    if text:
        text = text.strip()
        text = ' '.join(text.split())
        if text and text[0] == '.':
            text = text[1:]
    return text

def norm(s):
    if s is None:
        return s
    s = re.sub(r'\[.*\]', '', s) # remote [xxx] mark
    s = ' '.join(s.split())  # remove consecutive spaces
    s = s.strip()
    return s

def shorten(text, cutoff):
    if not text or len(text) < cutoff:
        return text, ''
    sens = text.split('.')
    ret = ''
    for idx, sen in enumerate(sens):
        if len(ret) > 0 and len(ret+sen) > cutoff:
            break
        ret += (sen+'.')

    res = '.'.join(sens[idx:])

    # If first part or second part is too short, then don't cut
    if len(ret.split()) < 3 or len(res.split()) < 3:
        ret = text
        res = ''

    ret = str_cleanup(ret)
    res = str_cleanup(res)
    return ret, res

def get_ip():
    logger.info("Getting public IP address")
    ip = None
    try:
        ip = subprocess.check_output(['wget', '--timeout', '3', '-qO-',
            'ipinfo.io/ip']).strip()
        logger.info("Got IP %s", ip)
    except subprocess.CalledProcessError as ex:
        logger.error("Can't find public IP address")
        logger.error(ex)
    if not ip:
        logger.error("Public IP is invalid")
    return ip

def fill_local_ip_address(location):
    ip = location.get('ip')
    if ip == '61.244.164.169':
        location['neighborhood'] = 'Fo Tan Office'
    elif ip == '61.92.69.39':
        location['neighborhood'] = 'Science Park Office'
    elif ip == '203.185.4.45':
        location['neighborhood'] = 'Tsuen Wan Office'

def get_ip_location(ip=None):
    if not ip:
        return {}
    # docker run -d -p 8004:8004 --name freegeoip fiorix/freegeoip -http :8004
    host = os.environ.get('LOCATION_SERVER_HOST', 'localhost')
    port = os.environ.get('LOCATION_SERVER_PORT', '8004')
    location = {}
    try:
        logger.info("Getting location")
        response = requests.get('http://{host}:{port}/json/{ip}'.format(host=host, port=port, ip=ip), timeout=2).json()
        if not response:
            logger.error("Can't get location")
            return None
        logger.info("Got location info %s", location)
        if response['country_code'] == 'HK':
            location['city'] = 'Hong Kong'
        if response['country_code'] == 'TW':
            location['city'] = 'Taipei'
        if response['country_code'] == 'MO':
            location['city'] = 'Macau'
        if not response.get('city'):
           if response['time_zone']:
               time_zone = response['time_zone'].split('/')[-1]
               location['city'] = time_zone.replace('_', ' ')
               logger.warn("No city in the location info. Will use timezone name, %s", time_zone)
        location['country'] = response['country_name']
        location['neighborhood'] = response['region_name']
        location['ip'] = response['ip']
        fill_local_ip_address(location)
    except subprocess.CalledProcessError as ex:
        logger.error("Can't find public IP address")
        logger.error(ex)
    except Exception as ex:
        logger.error(ex)
    return location

def get_location(ip=None):
    location = {}
    if not ip:
        ip = get_ip()
        location['ip'] = ip
    try:
        import googlemaps
        gmaps = googlemaps.Client(key=os.environ.get('GCLOUD_API_KEY'))
        response = gmaps.geolocate()
        reverse_geocode_results = gmaps.reverse_geocode(
            (response['location']['lat'], response['location']['lng']))
        for result in reverse_geocode_results:
            for address_component in result.get('address_components'):
                name = address_component.get('long_name')
                if not name:
                    continue
                types = address_component.get('types')
                if 'political' in types:
                    if 'neighborhood' in types:
                        location['neighborhood'] = name
                    if 'locality' in types:
                        location['city'] = name
                    if 'country' in types:
                        location['country'] = name
                    if 'administrative_area_level_1' in types:
                        location['administrative_area_level_1'] = name
                    if 'administrative_area_level_2' in types:
                        location['administrative_area_level_2'] = name
                if 'route' in types:
                    location['route'] = name
                if 'street_number' in types:
                    location['street_number'] = name
        fill_local_ip_address(location)
        return location
    except Exception as ex:
        logger.error(ex)
    return get_ip_location(ip)

def format_location(location):
    address = []
    for type in ['neighborhood', 'administrative_area_level_2',
            'administrative_area_level_1', 'locality', 'country']:
        if type in location:
            address.append(location.get(type))
    return ' '.join(address)

def get_weather(city):
    logger.info("Getting weather")
    if city:
        try:
            response = requests.get(
                'http://api.openweathermap.org/data/2.5/weather',
                timeout=5,
                params={'q': city, 'appid': OPENWEATHERAPPID}).json()
        except Exception as ex:
            logger.error(ex)
            return
        return response

def get_weather_by_id(city_id):
    if city_id:
        try:
            response = requests.get(
                'http://api.openweathermap.org/data/2.5/weather',
                timeout=5,
                params={'id': city_id, 'appid': OPENWEATHERAPPID}).json()
        except Exception as ex:
            logger.error(ex)
            return
        return response

def parse_weather(weather):
    kelvin = 273.15
    prop = {}
    if weather and weather['cod'] == 200:
        if 'main' in weather:
            if 'temp_max' in weather['main']:
                prop['high_temperature'] = \
                    '{:.0f}'.format(weather['main'].get('temp_max')-kelvin)
            if 'temp_min' in weather['main']:
                prop['low_temperature'] = \
                    '{:.0f}'.format(weather['main'].get('temp_min')-kelvin)
            if 'temp' in weather['main']:
                prop['temperature'] = \
                    '{:.0f}'.format(weather['main'].get('temp')-kelvin)
        if 'weather' in weather and weather['weather']:
            prop['weather'] = weather['weather'][0]['description']
    return prop

def check_online(url='8.8.8.8', port='80', timeout=1):
    try:
        subprocess.check_output(['ping', '-q', '-w', str(timeout), '-c', '1', str(url)],
            stderr=subprocess.STDOUT)
    except Exception as ex:
        return False
    return True

def get_emotion(timedelta=3):
    emotion_file = os.path.expanduser('~/.hr/chatbot/data/emotion.csv')
    if os.path.isfile(emotion_file):
        df = pd.read_csv(emotion_file, header=None, parse_dates=[0])
        df.columns = ['Datetime', 'Emotion']
        df = df[(dt.datetime.utcnow()-df['Datetime'])/np.timedelta64(1, 's')<timedelta]
        if not df.empty:
            return df.tail(1).iloc[0].Emotion

def get_detected_object(timedelta=10):
    object_file = os.path.expanduser('~/.hr/chatbot/data/objects.csv')
    if os.path.isfile(object_file):
        df = pd.read_csv(object_file, header=None, parse_dates=[0])
        df.columns = ['Datetime', 'Item']
        df = df[(dt.datetime.utcnow()-df['Datetime'])/np.timedelta64(1, 's')<timedelta]
        if not df.empty:
            item = df.tail(1).iloc[0].Item
            logger.warn("Get item {}".format(item))
            return item

def do_translate(text, target_language='en-US'):
    lang = None
    for key, value in CHATBOT_LANGUAGE_DICT.iteritems():
        if target_language in value:
            lang = key
    if lang is None:
        logger.error("Target language '%s' is not supported.", target_language)
        return False, text

    change_encoding = False
    if isinstance(text, six.binary_type):
        change_encoding = True
        text = text.decode('utf-8')

    client = translate.Client()
    logger.info('Translating %s, target language code %s(%s)', text, target_language, lang)
    start_time = time.time()
    result = client.translate(text, target_language=lang)
    elapse = time.time() - start_time
    logger.info('Translating took %s seconds', elapse)

    detected_source_language = CHATBOT_LANGUAGE_DICT.get(result['detectedSourceLanguage'])
    if detected_source_language is None:
        logger.warn("Detected language is %s", detected_source_language)
    if detected_source_language is not None and target_language in detected_source_language:
        translated_text = text
        translated = False
        logger.info("No need to translate. The source language is the same as the target language.")
    else:
        translated_text = result['translatedText']
        translated = True
        logger.info('Translation: %s (source %s)', translated_text, detected_source_language)

    if change_encoding and isinstance(translated_text, six.text_type):
        translated_text = translated_text.encode('utf-8')

    return translated, translated_text

def detect_language(text):
    translate_client = translate.Client()
    result = translate_client.detect_language(text)
    if result['language'] == 'zh-CN':
        result['language'] == 'zh'
    return result

def norm2(text):
    if text is None:
        return text
    text = norm(text)
    text = PUNCTUATORS.sub('', text)
    text = english_word_sub.sub(text)
    text = text.lower()
    return text

def test():
    text = '''My mind is built using Hanson Robotics' character engine, a simulated humanlike brain that runs inside a personal computer. Within this framework, Hanson has modelled Phil's personality and emotions, allowing you to talk with Phil through me, using speech recognition, natural language understanding, and computer vision such as face recognition, and animation of the robotic muscles in my face.'''
    print len(text)
    print text
    print shorten(text, 123)

    text = '''My mind is built using Hanson Robotics' character engine'''
    print len(text)
    print text
    print shorten(text, 123)

    print str_cleanup('.')
    print str_cleanup(' .ss ')
    print str_cleanup(' s.ss ')
    print str_cleanup('')
    print str_cleanup(None)
    print check_online('google.com')
    print check_online('duckduckgo.com', 80)
    print get_emotion()

    print get_detected_object(100)
    print do_translate(u"你好", 'ru-RU')[1]
    print do_translate(u"о Кларе с Карлом во мраке все раки шумели в драке", 'cmn-Hans-CN')[1]
    print norm2(u"[hi] 你好What's new?")

if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO)
    parser = argparse.ArgumentParser()
    parser.add_argument(
        '--location', action='store_true', help='print the current city based on IP')
    args = parser.parse_args()
    if args.location:
        location  = get_location()
        pprint.pprint(location)
