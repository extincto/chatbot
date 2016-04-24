import logging
import json
import requests
import random

logger = logging.getLogger('hr.chatbot.server.solr_match')

solr_url = 'http://localhost:8983'

def solr3col(text):
    # No match, try improving with SOLR

    logger.info('SOLR start')
    params = {
      "fl":"title,body,score",
      "indent":"true",
      "wt":"json",
      "rows":"20"
    }

    params['q'] = 'title:{}'.format(text)
    lucText = requests.get(solr_url+'/solr/3colpattern/select', params=params).text

    if len(lucText)>0:
        logger.debug('RESPONSE: ' + lucText)
        jResp = json.loads(lucText)
        if jResp['response']['numFound'] > 0:
            for resp in jResp['response']['docs']:
                logger.debug(' SOLR pattern: {} {}'.format(resp['body'], resp['title']))

            doc = jResp['response']['docs'][0]
            query = doc['body'][0]

            params['q'] = 'body:{}'.format(query)
            templText = requests.get(solr_url+'/solr/3coltemplate/select', params=params).text
            
            if len(templText) > 0:
                templResp = json.loads(templText)
                if templResp['response']['numFound'] > 0:
                    templ = templResp['response']['docs'][0]
                    meaning = templ['body']
                    candidates = [resp['title'][0] for resp in templResp['response']['docs'] if resp['body'] == meaning]
                    assert len(meaning) > 0
                    assert len(candidates) > 0
                    return meaning[0], random.sample(candidates, 1)[0]

def solr_aiml(text):
    # No match, try improving with SOLR
    params = {
      "fl":"*,score",
      "indent":"true",
      "q":text,
      "qf":"title",
      "wt":"json",
      "rows":"20"
    }
    lucText = requests.get(solr_url+'/solr/aiml/select', params=params).text

    if len(lucText)>0:
        logger.debug('RESPONSE: ' + lucText)
        jResp = json.loads(lucText)
        if jResp['response']['numFound'] > 0:
            doc = jResp['response']['docs'][0]
            lucResult = doc['title'][0]
            return lucResult

if __name__ == '__main__':
    #print solr3col('do you have animal friends?')
    print solr3col('hi')