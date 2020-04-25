import pywikibot

import pandas as pd
from tabulate import tabulate

import requests
import numpy as np
import mwparserfromhell as mwp
from wikitables import import_tables, WikiTable
from wikitables.util import ftag

crosswalk_page_name = 'User:Fuzheado/Met/glamingest/objectName'
wikidata_api_url = 'https://www.wikidata.org/w/api.php'


def import_tables_from_wikitext(wikitext, title=None):
    # Set default title value
    if title is None:
        title = 'generic'

    body = wikitext

    ## parse for tables
    raw_tables = mwp.parse(body).filter_tags(matches=ftag('table'))

    def _table_gen():
        for idx, table in enumerate(raw_tables):
            name = '%s[%s]' % (title, idx)
            yield WikiTable(name, table)

    return list(_table_gen())


def import_tables_from_url(api_url, title):
    params = {'prop': 'revisions',
              'format': 'json',
              'action': 'query',
              'explaintext': '',
              'titles': title,
              'rvprop': 'content'}

    r = requests.get(api_url, params)
    r.raise_for_status()
    pages = r.json()["query"]["pages"]

    # use key from first result in 'pages' array
    pageid = list(pages.keys())[0]
    if pageid == '-1':
        raise ArticleNotFound('no matching articles returned')

    page = pages[pageid]
    body = page['revisions'][0]['*']

    return import_tables_from_wikitext(body, page['title'])


def import_tables_from_url_full(api_url, title):
    params = {'prop': 'revisions',
              'format': 'json',
              'action': 'query',
              'explaintext': '',
              'titles': title,
              'rvprop': 'content'}

    r = requests.get(api_url, params)
    r.raise_for_status()
    pages = r.json()["query"]["pages"]

    # use key from first result in 'pages' array
    pageid = list(pages.keys())[0]
    if pageid == '-1':
        raise ArticleNotFound('no matching articles returned')

    page = pages[pageid]
    body = page['revisions'][0]['*']

    ## parse for tables
    raw_tables = mwp.parse(body).filter_tags(matches=ftag('table'))

    def _table_gen():
        for idx, table in enumerate(raw_tables):
            name = '%s[%s]' % (page['title'], idx)
            yield WikiTable(name, table)

    return list(_table_gen())


site = pywikibot.Site('wikidata', 'wikidata')
toah_count_page = pywikibot.Page(site, u'User:Fuzheado/Met/TOAH/objectName_count')
crosswalk_page = pywikibot.Page(site, u'User:Fuzheado/Met/glamingest/objectName')

# Process tables via Pywikibot and parsing text
crosswalk_text = crosswalk_page.text
wikitext_tables = import_tables_from_wikitext(crosswalk_text)
# print(crosswalk_text)
crosswalk_from_pywikibot_df = pd.read_json(wikitext_tables[0].json()).rename(columns={'QID': 'qid'}).replace(r'^\s*$',
                                                                                                             np.nan,
                                                                                                             regex=True)
print(crosswalk_from_pywikibot_df.info())
print(crosswalk_from_pywikibot_df.head(10))

# Process tables via API call, JSON
api_tables = import_tables_from_url(wikidata_api_url, crosswalk_page_name)
crosswalk_from_apicall_df = pd.read_json(api_tables[0].json()).rename(columns={'QID': 'qid'}).replace(r'^\s*$', np.nan,
                                                                                                      regex=True)
print(crosswalk_from_apicall_df.info())
print(crosswalk_from_apicall_df.head(10))

# Process tables via pywikibot
