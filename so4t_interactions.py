'''
This Python script is offered with no formal support. 
If you run into difficulties, reach out to the person who provided you with this script.
'''

# Standard library imports
import argparse
import json
import os
import time

# Third-party library imports
import requests
import pandas as pd
from bs4 import BeautifulSoup
from d3blocks import D3Blocks
from selenium import webdriver
from selenium.webdriver.chrome.service import Service


def main():

    args = get_args()
    users, questions = data_collector(args)
    interaction_matrix = data_processor(users, questions)
    create_chord_diagram(interaction_matrix)


def get_args():

    parser = argparse.ArgumentParser(
        prog='so4t_interactions.py',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        description='Grab data from Stack Overflow for Teams and create \
        a chord diagram of cross-silo interactions',
        epilog = 'Usage examples: \n'
                'python3 so4t_interactions.py --url "https://SUBDOMAIN.stackoverflow.com" '
                '--token "YOUR_TOKEN" \n\n'
                'python3 so4t_interactions.py --url "https://SUBDOMAIN.stackenterprise.co" '
                '--key "YOUR_KEY" \n\n')
    parser.add_argument('--url', 
                        type=str, 
                        help='[REQUIRED] Base URL for Stack Overflow for Teams site')
    parser.add_argument('--key',
                        type=str,
                        help='API key. Only required for Stack Overflow Enterprise sites')
    parser.add_argument('--token',
                        type=str,
                        help='API token. Only required for Stack Overflow Business sites')

    return parser.parse_args()


def data_collector(args):

    s = create_session(args.url)
    client = V2Client(args)

    users = get_user_data(s, client, args.url)
    questions = get_question_data(client)

    return users, questions


class V2Client(object):

    def __init__(self, args):

        if not args.url:
            print("Missing required argument. Please provide a URL.")
            print("See --help for more information")
            raise SystemExit
        
        if "stackoverflowteams.com" in args.url:
            self.soe = False
            self.api_url = "https://api.stackoverflowteams.com/2.3"
            self.team_slug = args.url.split("https://stackoverflowteams.com/c/")[1]
            self.token = args.token
            self.api_key = None
            self.headers = {'X-API-Access-Token': self.token}
            if not self.token:
                print("Missing required argument. Please provide an API token.")
                print("See --help for more information")
                raise SystemExit
        else:
            self.soe = True
            self.api_url = args.url + "/api/2.3"
            self.team_slug = None
            self.token = None
            self.api_key = args.key
            self.headers = {'X-API-Key': self.api_key}
            if not self.api_key:
                print("Missing required argument. Please provide an API key.")
                print("See --help for more information")
                raise SystemExit

        self.ssl_verify = self.test_connection()


    def test_connection(self):

        url = self.api_url + "/tags"
        ssl_verify = True

        params = {}
        if self.token:
            headers = {'X-API-Access-Token': self.token}
            params['team'] = self.team_slug
        else:
            headers = {'X-API-Key': self.api_key}

        print("Testing API 2.3 connection...")
        try:
            response = requests.get(url, params=params, headers=headers)
        except requests.exceptions.SSLError:
            print("SSL error. Trying again without SSL verification...")
            response = requests.get(url, params=params, headers=headers, verify=False)
            ssl_verify = False
        
        if response.status_code == 200:
            print("API connection successful")
            return ssl_verify
        else:
            print("Unable to connect to API. Please check your URL and API key.")
            print(response.text)
            raise SystemExit


    def get_all_questions(self, filter_string=''):

        endpoint = "/questions"
        endpoint_url = self.api_url + endpoint

        params = {
            'page': 1,
            'pagesize': 100,
        }
        if filter_string:
            params['filter'] = filter_string
    
        return self.get_items(endpoint_url, params)


    def get_all_users(self, filter_string=''):
            
            endpoint = "/users"
            endpoint_url = self.api_url + endpoint
    
            params = {
                'page': 1,
                'pagesize': 100,
            }
            if filter_string:
                params['filter'] = filter_string
    
            return self.get_items(endpoint_url, params)
    

    def create_filter(self, filter_attributes='', base='default'):
        # filter_attributes should be a list variable containing strings of the attributes
        # base can be 'default', 'withbody', 'none', or 'total'

        endpoint = "/filters/create"
        endpoint_url = self.api_url + endpoint

        params = {
            'base': base,
            'unsafe': False
        }

        if filter_attributes:
            # convert to semi-colon separated string
            params['include'] = ';'.join(filter_attributes)

        filter_string = self.get_items(endpoint_url, params)[0]['filter']
        print(f"Filter created: {filter_string}")

        return filter_string


    def get_items(self, endpoint_url, params={}):

        if not self.soe: # SO Basic and Business instances require a team slug in the params
            params['team'] = self.team_slug

        items = []
        while True: # Keep performing API calls until all items are received
            if params.get('page'):
                print(f"Getting page {params['page']} from {endpoint_url}")
            else:
                print(f"Getting API data from {endpoint_url}")
            response = requests.get(endpoint_url, headers=self.headers, params=params, 
                                    verify=self.ssl_verify)
            
            if response.status_code != 200:
                # Many API call failures result in an HTTP 400 status code (Bad Request)
                # To understand the reason for the 400 error, specific API error codes can be 
                # found here: https://api.stackoverflowteams.com/docs/error-handling
                print(f"/{endpoint_url} API call failed with status code: {response.status_code}.")
                print(response.text)
                print(f"Failed request URL and params: {response.request.url}")
                raise SystemExit

            items += response.json().get('items')
            if not response.json().get('has_more'): # If there are no more items, break the loop
                break

            # If the endpoint gets overloaded, it will send a backoff request in the response
            # Failure to backoff will result in a 502 error (throttle_violation)
            if response.json().get('backoff'):
                backoff_time = response.json().get('backoff') + 1
                print(f"API backoff request received. Waiting {backoff_time} seconds...")
                time.sleep(backoff_time)

            params['page'] += 1

        return items


def get_user_data(s, client, base_url):

    users = client.get_all_users()

    no_org_count = 0
    for user in users:
        user_url = f"{base_url}/users/{user['user_id']}"

        print(f'Getting user info for {user_url}')
        response = s.get(user_url)
        soup = BeautifulSoup(response.text, 'html.parser')
        title_org = soup.find('div', {'class': 'mb8 fc-light fs-title lh-xs'})
        try:
            user['organization'] = title_org.text.split(', ')[-1]
        except AttributeError: # if no title/org returned, `text` method will not work on None
            no_org_count += 1
            user['organization'] = None
        except IndexError: # if using old title format
            no_org_count += 1
            user['organization'] = None

    return users


def get_question_data(client):

    # Create a filter to get additional data fields for questions/answers/comments
    if client.soe: # For SO Enterprise, create a custom filter
        filter_attributes = [
            "answer.comment_count",
            "answer.comments",
            "answer.down_vote_count",
            "answer.up_vote_count",
            "question.answers",
            "question.comment_count",
            "question.comments",
            "question.down_vote_count",
            "question.up_vote_count",
        ]
        filter_string = client.create_filter(filter_attributes)
    else: # As of 2023.08.14 filter creation is not working for SO Business
        filter_string = '!)Rm-Ag_bMMFYDy3UqfEQNPt7'

    questions = client.get_all_questions(filter_string)

    return questions


def create_session(base_url):

    service = Service()
    options = webdriver.ChromeOptions()
    options.add_argument("--window-size=500,800")
    options.add_experimental_option("excludeSwitches", ['enable-automation'])
    driver = webdriver.Chrome(service=service, options=options)
    driver.get(base_url)

    while True:
        try:
            # Element names for selenium: 
            # https://selenium-python.readthedocs.io/locating-elements.html
            driver.find_element("class name", "s-user-card")
            break
        except:
            time.sleep(1)
    
    # pass cookies to requests
    cookies = driver.get_cookies()
    s = requests.Session()
    for cookie in cookies:
        s.cookies.set(cookie['name'], cookie['value'])
    driver.close()
    driver.quit()
    
    return s


def get_page_count(s, url):

    response = s.get(url)
    soup = BeautifulSoup(response.text, 'html.parser')
    pagination = soup.find_all('a', {'class': 's-pagination--item js-pagination-item'})
    page_count = int(pagination[-2].text)

    return page_count


def data_processor(users, questions):

    interaction_data, untracked_interactions = create_interaction_data(questions, users, questions)
    print(f"Number of interactions not tracked due to deleted users: {untracked_interactions}")

    interaction_matrix = create_interaction_matrix(interaction_data)

    return interaction_matrix

# Should split this into smaller functions
def create_interaction_data(content_list, users, questions):

    interaction_data = []
    untracked_interactions = 0

    for content in content_list:
        interaction = {
            'source_user': validate_user_id(content['owner']),
            'source_org': None,
            'interacting_users': [],
            'interacting_orgs': [],
            'post_type': None,
            'id': None,
            'tags': None # only for questions
        }
        interaction['source_org'] = find_user_org(interaction['source_user'], users)

        # if there is no user_id, the user has been deleted; cannot properly track interactions
        # tally untracked interactions, end the loop, and move on to the next content object
        if not interaction['source_user']:
            interaction_count = 0

            # this falsely assumes users can't answer their own questions
            try:
                interaction_count += len(content['answers'])
            except KeyError: # if there are no answers
                pass

            # Need to verify comments are not from the source user to avoid double counting
            # CAN USE NEW VALIDATE_USER_ID FUNCTION TO CHECK FOR DELETED USERS
            try:
                interaction_count += len(content['comments'])
            except KeyError:
                pass
            untracked_interactions += interaction_count
            continue

        try:
            interaction['id'] = content['answer_id']
            interaction['post_type'] = 'answer'
        except KeyError: # if there is no answer_id, it's a question
            interaction['id'] = content['question_id']
            interaction['post_type'] = 'question'
            interaction['tags'] = content['tags']

        if interaction['post_type'] == 'answer':
            original_question = find_original_question(content['question_id'], questions)
            interaction['tags'] = original_question['tags']
        else:
            original_question = None
        
        try:
            for answer in content['answers']:
                interaction, untracked_interactions = add_user_and_org(
                    interaction, answer, untracked_interactions, users)
            
            interactions, untracked = create_interaction_data(content['answers'], users, questions)
            interaction_data += interactions
            untracked_interactions += untracked
        except KeyError: # if there are no answers
            pass
        
        try:
            for comment in content['comments']:
                try:
                    original_asker = validate_user_id(original_question['owner'])
                    commenter = validate_user_id(comment['owner'])
                    if original_asker == commenter:
                        continue # do not record comment interactions from the question owner
                except TypeError: # if comment is on a question, original_question will not exist
                    pass
                interaction, untracked_interactions = add_user_and_org(
                    interaction, comment, untracked_interactions, users)
        except KeyError: # if there are no comments
            if interaction['post_type'] == 'answer': # do not record answers with no comments
                continue
            pass

        interaction_data.append(interaction)

    return interaction_data, untracked_interactions


def validate_user_id(user):
    # If the user doesn't exist (e.g. deleted), the user_id will not be present
    # Likewise, the user_type will be "does_not_exist"

    try:
        return user['user_id']
    except KeyError:
        return None
    

def find_user_org(user_id, users):

    search_result = next((item for item in users if int(item['user_id']) == user_id), None)
    try:
        user_org = search_result['organization']
    except TypeError: # if None is returned from the search_result
        user_org = search_result
    
    return user_org


def find_original_question(question_id, questions):

    search_result = next((item for item in questions if int(item['question_id']) == question_id), None)
    
    return search_result


def add_user_and_org(interaction, content, untracked_interactions, users):

    source_user = interaction['source_user']
    interacting_users = interaction['interacting_users']
    new_user = validate_user_id(content['owner'])

    if not new_user: # if the user has been deleted
        untracked_interactions += 1
    else:
        if new_user != source_user and new_user not in interacting_users:
            interaction['interacting_users'].append(new_user)
            interacting_org = find_user_org(new_user, users)
            if not interacting_org: # unable to properly track interaction if there is no org
                untracked_interactions += 1
            elif interacting_org not in interaction['interacting_orgs']:
                interaction['interacting_orgs'].append(find_user_org(new_user, users))

    return interaction, untracked_interactions


def create_interaction_matrix(interaction_data):

    matrix_data = []
    for interaction in interaction_data:
        if interaction['post_type'] == 'question':
            source_org = interaction['source_org']
        else: # if it's an answer
            target_org = interaction['source_org']
        
        interacting_orgs = interaction['interacting_orgs']
        for org in interacting_orgs:
            if source_org:
                matrix_data.append({
                    'source': source_org,
                    'target': org
                })
            else: # if it's an answer
                matrix_data.append({
                    'source': org,
                    'target': target_org
                })
    
    interaction_matrix = pd.DataFrame(matrix_data).groupby(['source', 'target']).size().reset_index(
        name='weight').pivot(index='source', columns='target', values='weight').fillna(0)
    interaction_matrix = interaction_matrix.astype(int)
    
    # export interaction matrix to csv
    file_name = 'interaction_matrix.csv'
    interaction_matrix.to_csv(file_name)
    print(f"{file_name} has been created in the current working directory.")

    return interaction_matrix


def create_chord_diagram(interaction_matrix):

    filepath = os.path.join(os.getcwd(), 'chord_diagram.html')
    d3_data = interaction_matrix.stack().reset_index().rename(
        columns={'level_0':'source','level_1':'target', 0:'weight'})
    
    d3 = D3Blocks()
    original_html = d3.chord(d3_data, 
                    color='source', 
                    opacity='source',
                    cmap='Set1',
                    filepath=None,
                    notebook=False)

    # change size and position of the svg
    modified_html = original_html.replace('-width / 2, -height / 2, width, height',
                                          'width - 1400, height - 1425, width + 200, height + 200')
    with open(filepath, 'w') as f:
        f.write(modified_html)

    print("Chord diagram created. You can find it in the current working directory.")


# Waiting on SCIM support for title/organization
def get_scim_users(scim_token, base_url):

    site_url = base_url
    scim_url = f"{site_url}/api/scim/v2/Users"
    headers = {
        'Authorization': f"Bearer {scim_token}"
    }
    params = {
        "count": 100,
        "startIndex": 1,
    }

    items = []
    while True: # Keep performing API calls until all items are received
        print(f"Getting 100 results from {scim_url} with startIndex of {params['startIndex']}")
        response = requests.get(scim_url, headers=headers, params=params)
        if response.status_code != 200:
            print(f"API call failed with status code: {response.status_code}.")
            print(response.text)
            break

        items_data = response.json().get('Resources')
        items += items_data

        params['startIndex'] += params['count']
        if params['startIndex'] > response.json().get('totalResults'):
            break

    return items


def export_to_json(data_name, data):

    file_name = f"{data_name}.json"

    with open(file_name, 'w') as f:
        json.dump(data, f)

    print(f"{file_name} has been created in the current working directory.")


if __name__ == '__main__':

    main()
