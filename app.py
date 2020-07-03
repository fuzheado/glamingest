# -*- coding: utf-8 -*-

import flask
import os
import yaml
import re
import pandas as pd
import numpy as np
import requests
from flask_bootstrap import Bootstrap
import json
import urllib.parse

import mwparserfromhell as mwp
from wikitables import import_tables, WikiTable
from wikitables.util import ftag

# from flask import request, jsonify

app = flask.Flask(__name__)

bootstrap = Bootstrap(app)

# Load configuration from YAML file
__dir__ = os.path.dirname(__file__)
app.config.update(
    yaml.safe_load(open(os.path.join(__dir__, 'config.yaml'))))

metdepartments = {
    'American Decorative Arts': 'Q67429123',
    'The American Wing': 'Q67429123',
    'Ancient Near Eastern Art': 'Q67429126',
    'Arms and Armor': 'Q67429127',
    'Arts of Africa, Oceania, and the Americas': 'Q67429128',
    'Asian Art': 'Q67429130',
    'Costume Institute': 'Q67087093',
    'Drawings and Prints': 'Q67429132',
    'Egyptian Art': 'Q67429133',
    'European Paintings': 'Q67429134',
    'European Sculpture and Decorative Arts': 'Q67429136',
    'Greek and Roman Art': 'Q67429137',
    'Islamic Art': 'Q67429139',
    'Medieval Art': 'Q67429140',
    'Modern and Contemporary Art': 'Q67429142',
    'Musical Instruments': 'Q67429143',
    'Photographs': 'Q67429146',
    'Robert Lehman Collection': 'Q67429147',
    'The Cloisters': 'Q1138030',
    'The Libraries': 'Q67429148'
}

# Commons categories for each department
# From: https://commons.wikimedia.org/wiki/Category:Metropolitan_Museum_of_Art_by_department
metdepartments_commons_category = {
    'American Decorative Arts': 'Department of American Decorative Arts, Metropolitan Museum of Art',
    'The American Wing': 'The American Wing Collection, Metropolitan Museum of Art‎',
    'Ancient Near Eastern Art': 'Department of Ancient Near Eastern Art, Metropolitan Museum of Art‎ ',
    'Arms and Armor': 'Department of Arms and Armor, Metropolitan Museum of Art‎',
    'Arts of Africa, Oceania, and the Americas': 'Department of Arts of Africa, Oceania, and the Americas, Metropolitan Museum of Art‎',
    'Asian Art': 'Department of Asian Art, Metropolitan Museum of Art‎',
    'Costume Institute': 'Costume Institute, Metropolitan Museum of Art‎',
    'Drawings and Prints': 'Department of Drawings and Prints, Metropolitan Museum of Art',
    'Egyptian Art': 'Department of Egyptian Art, Metropolitan Museum of Art‎',
    'European Paintings': 'Department of European Paintings, Metropolitan Museum of Art‎',
    'European Sculpture and Decorative Arts': 'Department of European Sculpture and Decorative Arts, Metropolitan Museum of Art‎',
    'Greek and Roman Art': 'Department of Greek and Roman Art, Metropolitan Museum of Art‎ ',
    'Islamic Art': 'Department of Islamic Art, Metropolitan Museum of Art‎',
    'Medieval Art': 'Department of Medieval Art, Metropolitan Museum of Art‎',
    'Modern and Contemporary Art': 'Department of Modern and Contemporary Art, Metropolitan Museum ',
    'Musical Instruments': 'Department of Musical Instruments, Metropolitan Museum of Art‎',
    'Photographs': 'Department of Photographs, Metropolitan Museum of Art‎',
    'Robert Lehman Collection': 'Robert Lehman Collection (Metropolitan Museum of Art)',
    'The Cloisters': 'The Cloisters Collection, Metropolitan Museum of Art‎',
    'The Libraries': 'Libraries Collection, Metropolitan Museum of Art‎'
}

# Need OAuth to use this
#   Options: urls and desc
url2commons_url = 'https://tools.wmflabs.org/url2commons/index.html'
sparql_api_url = 'https://query.wikidata.org/bigdata/namespace/wdq/sparql'
commons_search_url = 'https://commons.wikimedia.org/w/index.php?sort=relevance&search={}&title=Special%3ASearch&profile=advanced&fulltext=1&advancedSearch-current=%7B%7D&ns0=1&ns6=1&ns14=1'

# Crosswalk database in Google Sheets, which is now moved to on-wiki
# met_objectname_sheet = 'https://docs.google.com/spreadsheets/d/1WmXW2CjlLidcUXzahQsB3HjUVvECns4xDyIt-Hw-jW8/export?format=csv&id=1WmXW2CjlLidcUXzahQsB3HjUVvECns4xDyIt-Hw-jW8&gid=0'

# Changed the method of ingesting the crosswalk to using a wiki page instead
# cw_df = pd.read_csv(met_objectname_sheet, header=0, usecols=["Object Name", "QID", "extrastatement", "extraqualifier"])

default_object_name = 'object'  # If the objectName cannot be found, default to this

# OLD page for dashboard/crosswalk
# objectname_crosswalk_page = 'User:Fuzheado/Met/glamingest/objectName'
objectname_crosswalk_page = 'Wikidata:GLAM/Metropolitan_Museum_of_Art/glamingest/objectName'
objectname_crosswalk_url = 'https://www.wikidata.org/wiki/' + objectname_crosswalk_page
wikidata_api_url = 'https://www.wikidata.org/w/api.php'

metapibase = 'https://collectionapi.metmuseum.org/public/collection/v1/objects/'
metobjbase = 'https://www.metmuseum.org/art/collection/search/'

# Wikidata reconciliation API - mapping names to Q items
# Example of escaped query - Pavel%20Petrovich%20Svinin
wdreconapibase = 'https://tools.wmflabs.org/openrefine-wikidata/en/api?query='

commons_template_met = '''\
=={{int:filedesc}}==
{{Artwork
 |artist             = __artist__
 |author             = 
 |title              = __title__
 |description        = __description__
 |object type        = __objectName__
 |date               = __objectDate__
 |medium             = __medium__
 |dimensions         = __dimensions__
 |institution        = {{Institution:Metropolitan Museum of Art}}
 |department         = __department__
 |accession number   = __accessionNumber__
 |place of creation  = 
 |place of discovery = 
 |object history     = 
 |exhibition history = 
 |credit line        = __creditLine__
 |inscriptions       = 
 |notes              = 
 |references         = 
 |source             = __objectURL__{{Template:TheMet}}
 |permission         = {{Cc-zero}}
 |other_versions     = 
 |wikidata           = __objectWikidata_URL__
 |other_fields       = 
}}
[[Category:__department_commons_category__]]
'''


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

    # parse for tables
    raw_tables = mwp.parse(body).filter_tags(matches=ftag('table'))

    def _table_gen():
        for idx, table in enumerate(raw_tables):
            name = '%s[%s]' % (page['title'], idx)
            yield WikiTable(name, table)

    return list(_table_gen())


@app.route('/')
def index():
    greeting = app.config['GREETING']
    username = flask.session.get('username', None)
    return flask.render_template(
        'index.html', username=username, greeting=greeting)


@app.route('/mettest')
def mettest():
    return flask.render_template('metid.html')


@app.route('/metid/<int:id>', methods=['GET'])
def metid(id):
    memo = []  # Set of messages to present to the user
    qs = []  # For building the Quickstatement
    resultlist = []  # Result for exploratory SPARQL query

    # Original fancy downcase function to turn Object Names like "Painting" to "painting"
    downcasefunc = lambda s: re.sub(r'; ', r'/', s.lower()) if isinstance(s, str) else 'object'

    # Create a Wikidata query to check if a Q item already exists - need to double escape {{ and }}
    basequery = '''
SELECT DISTINCT ?item ?instance ?collection ?inventory ?location ?copyright ?ccurl WHERE {{ 
  ?item wdt:P3634 "{}" .
  OPTIONAL {{ ?item wdt:P31 ?instance }}
  OPTIONAL {{ ?item wdt:P195 ?collection }}
  OPTIONAL {{ ?item wdt:P217 ?inventory }}
  OPTIONAL {{ ?item wdt:P276 ?location }}
  OPTIONAL {{ ?item wdt:P6216 ?copyright }}
  OPTIONAL {{ ?item wdt:P4765 ?ccurl }}
}} LIMIT 1000
'''
    query = basequery.format(id)  # Insert Met Object ID

    # Create UI forward and backward buttons
    forward_id = id + 1
    backward_id = id - 1
    navlinks = {
        "forward_id": str(forward_id),
        "backward_id": str(backward_id)
    }

    qid = ''  # For storing existing qids
    display_img = None

    # Set up Met API and Object URLs
    metapicall = metapibase + str(id)
    metobjcall = metobjbase + str(id)

    # Perform SPARQL query
    try:
        data = requests.post(sparql_api_url, data={'query': query, 'format': 'json'}).json()
        memo.append(json.dumps(data))
    except ValueError:
        flask.render_template('metid.html',
                              img=display_img,
                              id=id,
                              qid=qid,
                              qs='',
                              memo='No API content returned',
                              memoList=memo,
                              url2commons_command='',
                              commons_search_command='',
                              objectname_crosswalk='',
                              metapicall=metapicall,
                              metobjcall=metobjcall,
                              **navlinks)

    for item in data['results']['bindings']:
        qid = item['item']['value'].replace('http://www.wikidata.org/entity/', '')
        resultlist.append(qid)
        memo.append('Found object ID in Wikidata: {}'.format(id))
    resultlist = list(set(resultlist))
    if len(resultlist) > 0:
        if len(resultlist) > 1:
            qs_subject = 'TOOMANY'
            memo.append(
                'Warning: multiple existing items for Met ID {} - {} Wikidata item(s)'.format(id, len(resultlist)))
        else:
            qs_subject = qid
            memo.append('Exact Wikidata match: {}'.format(qid))
    else:
        # No Wikidata item
        # Start the Quickstatement with CREATE if this is a new item
        qs.append('CREATE')
        # Use LAST as the subject the Quickstatement triples
        qs_subject = 'LAST'
        memo.append('Cleared for item creation: no Wikidata results returned for this object ID')

    glamqid = 'Q160236'
    wikidata_pd = 'Q19652'
    simpledate_template = '+{}-00-00T00:00:00Z/9'
    circa_date_qualifier = '|P1480|Q5727902'  # Added to date statement for circa
    latest_date_qualifier = '|P1326|+{}-00-00T00:00:00Z/9'  # Add statement for latest date

    crosswalk_table = {
        'wdLabel': '{}|Len|"{}"',
        'wdDescription': '{}|Den|"{} (MET, {})"',
        'wdLocation': '{}|P276|{}',
        'wdCommonsCompatible': '{}|P4765|"{}"',
        'wdCopyrightStatus': '{}|P6216|{}|P459|Q61848113',
        'objectID': '{}|P3634|"{}"',
        'accessionNumber': '{}|P217|"{}"|P195|{}',
        'collection': '{}|P195|{}|P217|"{}"',
        'objectName': '{}|P31|{}',
        'objectDate': '{}|P571|{}',
        'isTimelineWork': '{}|P1343|Q28837176'
    }

    # data = json.loads(rawdata, strict=False)
    data = requests.get(metapicall).json()

    # Check to see if nothing comes back
    if 'message' in data:
        memo.append('Object ID not in use')
    if 'title' in data:
        qs.append(crosswalk_table['wdLabel'].format(qs_subject, data['title']))

    if 'objectID' in data:
        qs.append(crosswalk_table['objectID'].format(qs_subject, data['objectID']))
    if 'accessionNumber' in data:
        qs.append(crosswalk_table['accessionNumber'].format(qs_subject, data['accessionNumber'], glamqid))

    if 'isTimelineWork' in data:
        if data['isTimelineWork']:
            # TODO - Add statement about TOAH
            # item|P1343|Q28837176
            qs.append(crosswalk_table['isTimelineWork'].format(qs_subject))
            memo.append('Timeline work: should add statements')
        else:
            memo.append('Not timeline work')

    if 'objectDate' in data:
        incomingdate = data['objectDate']
        # Simple exact date of all digits
        if incomingdate.isdigit():
            date = simpledate_template.format(data['objectDate'])
            qs.append(crosswalk_table['objectDate'].format(qs_subject, date))
        else:
            # Test for simple circa date like 1882
            matched = re.match(r"^ca. (\d+)$", incomingdate)
            if matched:
                date = simpledate_template.format(matched.group(1))
                qs.append(crosswalk_table['objectDate'].format(qs_subject, date) + circa_date_qualifier)
                memo.append('Date: Found simple circa date: ' + incomingdate)
            else:
                # Test for dates like circa 969-1000 or 1882-89
                matched = re.match(r"^ca. (\d+)–(\d+)$", incomingdate)
                if matched:
                    # Generate the base date for the statement from first match
                    date = simpledate_template.format(matched.group(1))
                    date_latest = None
                    memo.append('Possible double circa: {} and {}'.format(matched.group(1), matched.group(2)))
                    # Test to see if second part of range is less than first, like 1882-89
                    if int(matched.group(1)) > int(matched.group(2)):
                        # Then it's like 1882-89
                        difference = len(matched.group(1)) - len(matched.group(2))
                        # Grab the first difference characters: 18
                        chopped_date_prefix = matched.group(1)[:difference]
                        # Add the chopped prefix to the date: 1889
                        date_latest = latest_date_qualifier.format(chopped_date_prefix + matched.group(2))
                    # Make the proper statement, with possibly two qualifiers
                    qs.append(
                        crosswalk_table['objectDate'].format(qs_subject, date) + circa_date_qualifier + str(
                            date_latest))
                    memo.append('Date: Found double circa date: ' + incomingdate)
                else:
                    memo.append('Date: Skipping since it is complex: ' + incomingdate)

    # Lookup the artist name using Wikidata reconciliation API
    if 'artistDisplayName' in data:
        if data['artistDisplayName']:
            reconquery = wdreconapibase + urllib.parse.quote_plus(data['artistDisplayName'])
            # print('reconquery: ' + reconquery)
            recondata = requests.get(reconquery).json()
            memo.append(json.dumps(recondata))
        # if recondata['result']:

        # TODO more sophisticated treatment of reconciliation, printing a link to help out
        # for item in recondata['result']:
        #     qid = item['item']['value'].replace('http://www.wikidata.org/entity/', '')
        #     resultlist.append(qid)
        #     memo.append('Found: {}'.format(qid))

        # Empty artistDisplayName, so assume unknown
        # else:

    # Grab images, first the large one for Commons, then a smaller display image
    primary_img = None
    if 'primaryImage' in data:
        if data['primaryImage']:
            primary_img = data['primaryImage']
    display_img = primary_img
    if 'primaryImageSmall' in data:
        if data['primaryImageSmall']:
            display_img = data['primaryImageSmall']

    # Determine creator_string as real artist name, or generically "at the Met"
    creator_string = " at the Metropolitan Museum of Art"
    if 'artistDisplayName' in data:
        if data['artistDisplayName']:
            creator_string = " by {}".format(data['artistDisplayName'])
        else:
            memo.append('Creator: not specified from API, using generic Met Museum for description')

    # Add collection Met, accession_number
    accession_number = None
    if 'accessionNumber' in data:
        accession_number = data['accessionNumber']
        qs.append(crosswalk_table['collection'].format(qs_subject, glamqid, accession_number))
        qs.append(crosswalk_table['wdLocation'].format(qs_subject, glamqid))

    url2commons_command = None
    commons_search_command = None
    if 'isPublicDomain' in data:
        if data['isPublicDomain']:
            qs.append(crosswalk_table['wdCommonsCompatible'].format(qs_subject, primary_img))
            qs.append(crosswalk_table['wdCopyrightStatus'].format(qs_subject, wikidata_pd))
            # TODO add more metadata about CC0, use Maarten's guidelines
            # https://www.wikidata.org/wiki/Q78609653
            # file format, url, title, author name string, license, operator

            # Fill in Artwork template for uploading to Commons, to be passed to url2commons
            # Start with the bare commons_template_met
            commons_template = commons_template_met
            creator_template = '{{{{Creator:{}}}}}'
            artist = ''
            if 'artistDisplayName' in data and data['artistDisplayName']:
                artist = creator_template.format(data['artistDisplayName'])
            # Craft the description in the
            template_description = ''
            if 'objectName' in data and data['objectName']:
                template_description = downcasefunc(data['objectName'])
                if 'culture' in data and data['culture']:
                    template_description = template_description + '; ' + data['culture']

            commons_template = re.sub('__artist__', artist, commons_template)
            commons_template = re.sub('__title__', data['title'], commons_template)
            commons_template = re.sub('__description__', template_description, commons_template)
            commons_template = re.sub('__department__', data['department'], commons_template)
            commons_template = re.sub('__objectName__', data['objectName'], commons_template)
            commons_template = re.sub('__objectDate__', data['objectDate'], commons_template)
            commons_template = re.sub('__medium__', data['medium'], commons_template)
            commons_template = re.sub('__dimensions__', data['dimensions'], commons_template)
            commons_template = re.sub('__accessionNumber__', data['accessionNumber'], commons_template)
            commons_template = re.sub('__creditLine__', data['creditLine'], commons_template)
            commons_template = re.sub('__objectURL__', data['objectURL'], commons_template)

            # See if there is Wikidata Q number from Met API
            try:
                found = re.search('.+(Q[0-9]+)$', data['objectWikidata_URL']).group(1)
            except AttributeError:
                found = ''  # No Wikidata, so leave blank
            commons_template = re.sub('__objectWikidata_URL__', found, commons_template)

            # Need to map department to Commons category
            commons_category = metdepartments_commons_category[data['department']]
            commons_template = re.sub('__department_commons_category__', commons_category, commons_template)

            # Craft the url2commons command to upload
            quoted_url = urllib.parse.quote(str.replace(primary_img, '_', '%5F'))
            url2commons_command = url2commons_url + '?urls=' + quoted_url + ' ' + \
                                  urllib.parse.quote(data['title'] + ' - MET ' + data['accessionNumber'] + '.jpg') + \
                                  '&desc=' + urllib.parse.quote(commons_template)

        else:
            # TODO - Add a message to main interface to say media is not free
            memo.append('Not public domain: Skip upload, no free version')

    # Setup the Commons search option, regardless of the PD status in case it's already in Commons
    # Set the basic search string for Commons
    commons_search_string = str(accession_number) + ' MET '
    if 'title' in data:
        if data['title']:
            commons_search_string += data['title']
    commons_search_command = commons_search_url.format(urllib.parse.quote_plus(commons_search_string))

    if 'department' in data:
        if data['department'] in metdepartments:
            qs.append(crosswalk_table['collection'].format(qs_subject, metdepartments[data['department']],
                                                           data['accessionNumber']))
        else:
            memo.append('Department: Skipped, none specified from API matched our crosswalk database')

    # Perform sophisticated Object Name mappings
    # TODO - take a look at classification as that is sometimes a better match
    #   id 33 - objectName = bust; classification = glass
    #   id 310175 - objectName = figure; classification = Stone-Sculpture
    # Lookup instance info in crosswalk
    entity_type = 'Object Name'
    entity_api_type = 'objectName'

    # Load crosswalk from wiki page, using wikitables to read it in
    tables = import_tables_from_url(wikidata_api_url, objectname_crosswalk_page)

    # Turn the wiki table into dataframe via JSON, while replacing blank cells with NaN
    cw_df = pd.read_json(tables[0].json()).replace(r'^\s*$', np.nan, regex=True)

    # Craft the Check for objectName
    if entity_api_type in data:

        memo.append('Met object name: {}'.format(data['objectName']))

        # Create description for Wikidata in the form of:
        # "painting (French) by Claude Monet (MET, 12.34)"
        if 'culture' in data and data['culture']:
            culture_string = ' (' + data['culture'] + ')'
        else:
            culture_string = ''
        wd_description = downcasefunc(data['objectName']) + culture_string + creator_string
        qs.append(crosswalk_table['wdDescription'].format(qs_subject,
                                                          wd_description,
                                                          data['accessionNumber']
                                                          ))
        entity = data[entity_api_type]
        entity_lookup = cw_df[cw_df[entity_type].str.match(u'^' + re.escape(entity) + '$')]

        entity_q = None
        entity_extrastatement_q = None

        if entity_lookup.empty:
            memo.append('Failed: object name lookup for "{}"'.format(entity))
            memo.append('Try adding object to crosswalk database: "{}"'.format('bitly link'))
        else:
            entity_q = entity_lookup[['QID']].iat[0, 0]
            entity_extrastatement_q = \
                cw_df[cw_df[entity_type].str.match('^' + re.escape(entity) + '$')][['extrastatement']].iat[0, 0]

        if isinstance(entity_q, str):
            # Generate Quickstatement via the string formatting pattern in the dict,
            # and use LAST as item
            qs.append(crosswalk_table[entity_api_type].format(qs_subject, entity_q))
            if isinstance(entity_extrastatement_q, str):
                qs.append(crosswalk_table[entity_api_type].format(qs_subject, entity_extrastatement_q))
    else:
        memo.append('Object name: Met did not specify. Skipped.')

    # Commented out since it is empty and not sure it's needed
    # memo.append('qid: '.format(qid))

    return flask.render_template('metid.html',
                                 img=display_img,
                                 id=id,
                                 qid=qid,
                                 qs='\n'.join(qs),
                                 memo='\n'.join(memo),
                                 memoList=memo,
                                 url2commons_command=url2commons_command,
                                 commons_search_command=commons_search_command,
                                 objectname_crosswalk=objectname_crosswalk_url,
                                 metapicall=metapicall,
                                 metobjcall=metobjcall,
                                 **navlinks)


if __name__ == '__main__':
    app.run()
