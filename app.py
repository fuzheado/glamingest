# -*- coding: utf-8 -*-

import flask
import os
import yaml
import re
import pandas as pd
import requests
from flask_bootstrap import Bootstrap
import json
import urllib.parse

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

# Need OAuth to use this
#   Options: urls and desc
url2commons_url = 'https://tools.wmflabs.org/url2commons/index.html'
wikidata_api_url = 'https://query.wikidata.org/bigdata/namespace/wdq/sparql'
commons_search_url = 'https://commons.wikimedia.org/w/index.php?sort=relevance&search={}&title=Special%3ASearch&profile=advanced&fulltext=1&advancedSearch-current=%7B%7D&ns0=1&ns6=1&ns14=1'

met_objectname_sheet = 'https://docs.google.com/spreadsheets/d/1WmXW2CjlLidcUXzahQsB3HjUVvECns4xDyIt-Hw-jW8/export?format=csv&id=1WmXW2CjlLidcUXzahQsB3HjUVvECns4xDyIt-Hw-jW8&gid=0'
cw_df = pd.read_csv(met_objectname_sheet, header=0, usecols=["Object Name", "QID", "extrastatement", "extraqualifier"])

default_object_name = 'object'  # If the objectName cannot be found, default to this


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
    # Perform SPARQL query
    data = requests.post(wikidata_api_url, data={'query': query, 'format': 'json'}).json()
    memo.append(json.dumps(data))

    qid = ''  # For storing existing qids

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

    metapibase = 'https://collectionapi.metmuseum.org/public/collection/v1/objects/'
    metapicall = metapibase + str(id)

    metobjbase = 'https://www.metmuseum.org/art/collection/search/'
    metobjcall = metobjbase + str(id)

    # Wikidata reconciliation API - mapping names to Q items
    # Example of escaped query - Pavel%20Petrovich%20Svinin
    wdreconapibase = 'https://tools.wmflabs.org/openrefine-wikidata/en/api?query='

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
        'wdCopyrightStatus': '{}|P6216|{}',
        'objectID': '{}|P3634|"{}"',
        'accessionNumber': '{}|P217|"{}"|P195|{}',
        'collection': '{}|P195|{}|P217|"{}"',
        'objectName': '{}|P31|{}',
        'objectDate': '{}|P571|{}'
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
                        crosswalk_table['objectDate'].format(qs_subject, date) + circa_date_qualifier + date_latest)
                    memo.append('Date: Found double circa date: ' + incomingdate)
                else:
                    memo.append('Date: Skipping since it is complex: ' + incomingdate)

    # Lookup the artist name using Wikidata reconciliation API
    if 'artistDisplayName' in data:
        reconquery = wdreconapibase + urllib.parse.quote_plus(data['artistDisplayName'])
        print('reconquery: ' + reconquery)
        recondata = requests.get(reconquery).json()
        memo.append(json.dumps(recondata))

        # if recondata['result']:

        # TODO more sophisticated treatment of reconciliation, printing a link to help out
        # for item in recondata['result']:
        #     qid = item['item']['value'].replace('http://www.wikidata.org/entity/', '')
        #     resultlist.append(qid)
        #     memo.append('Found: {}'.format(qid))

    # Grab images, first the large one for Commons, then a smaller display image
    primary_img = None
    if 'primaryImage' in data:
        if data['primaryImage']:
            primary_img = data['primaryImage']
    display_img = primary_img
    if 'primaryImageSmall' in data:
        if data['primaryImageSmall']:
            display_img = data['primaryImageSmall']

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
            # Craft the url2commons command to upload
            url2commons_command = url2commons_url + '?urls=' + urllib.parse.quote_plus(primary_img) + '_' + \
                                  urllib.parse.quote_plus(data['title'] + ' MET ' + data['accessionNumber'] + '.jpg')

        else:
            # TODO - Add a message to main interface to say it's not free
            memo.append('Not public domain: Skip upload, no free version')

    # Setup the Commons search option, regardless of the PD status in case it's already in Commons
    # Set the basic search string for Commons
    commons_search_string = 'MET ' + accession_number + ' '
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

    if 'artistDisplayName' in data:
        if data['artistDisplayName']:
            creator_string = " by {}".format(data['artistDisplayName'])
        else:
            creator_string = " at the Metropolitan Museum of Art"
            memo.append('Creator: not specified from API, using generic Met Museum for description')

    # Perform sophisticated Object Name mappings

    # Lookup instance info in crosswalk
    entity_type = 'Object Name'
    entity_api_type = 'objectName'

    # Craft the Check for objectName
    if entity_api_type in data:

        memo.append('Met object name: {}'.format(data['objectName']))

        qs.append(crosswalk_table['wdDescription'].format(qs_subject,
                                                          downcasefunc(data['objectName']) + creator_string,
                                                          data['accessionNumber']
                                                          ))
        entity = data[entity_api_type]

        entity_lookup = cw_df[cw_df[entity_type].str.match(u'^' + re.escape(entity) + '$')]

        if entity_lookup.empty:
            entity_q = None
            entity_extrastatement_q = None
            memo.append('Failed: object name lookup for "{}"'.format(entity))
            memo.append('Try adding object to crosswalk database: "{}"'.format('bitly link'))
        else:
            entity_q = entity_lookup[['QID']].iat[0, 0]
            entity_extrastatement_q = cw_df[cw_df[entity_type].str.match('^' + entity + '$')][['extrastatement']].iat[
                0, 0]

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
                                 metapicall=metapicall,
                                 metobjcall=metobjcall,
                                 **navlinks)


if __name__ == '__main__':
    app.run()
