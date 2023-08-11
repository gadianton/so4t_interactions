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
                'python3 so4t_interactions.py --url "https://SUBDOMAIN.stackenterprise.co" '
                '--key "YOUR_KEY" \n\n')
    parser.add_argument('--url', 
                        type=str, 
                        help='[REQUIRED] Base URL for Stack Overflow for Teams site')
    parser.add_argument('--key',
                        type=str,
                        help='[REQUIRED] API key for Stack Overflow for Teams site')

    return parser.parse_args()


def data_collector(args):

    base_url = args.url
    key = args.key

    client = TeamsClient(base_url, key)
    users = get_users(base_url, client)
    questions = client.get_all_questions(
        filter_id='!-(C9p6W5zHzR.xzw(UcCeR(6Z.YqYklUgN-bcu69o-O71EcDlgKKXF)q3H')
    
    return users, questions


class TeamsClient(object):

    def __init__(self, base_url, api_key):

        if "stackoverflowteams.com" in base_url:
            self.api_url = "https://api.stackoverflowteams.com/2.3"
            self.team_slug = base_url.split("https://stackoverflowteams.com/c/")[1]
            self.token = api_key
            self.api_key = None
        else:
            self.api_url = base_url + "/api/2.3"
            self.team_slug = None
            self.token = None
            self.api_key = api_key


    def get_all_questions(self, filter_id=''):

        endpoint = "/questions"
        endpoint_url = self.api_url + endpoint
    
        return self.get_items(endpoint_url, filter_id)


    def get_all_users(self, filter_id=''):

        endpoint = "/users"
        endpoint_url = self.api_url + endpoint

        return self.get_items(endpoint_url, filter_id)


    def get_items(self, endpoint_url, filter_id):
        
        params = {
            'page': 1,
            'pagesize': 100,
        }
        if filter_id:
            params['filter'] = filter_id

        if self.token:
            headers = {'X-API-Access-Token': self.token}
            params['team'] = self.team_slug
        else:
            headers = {'X-API-Key': self.api_key}


        items = []
        while True: # Keep performing API calls until all items are received
            print(f"Getting page {params['page']} from {endpoint_url}")
            response = requests.get(endpoint_url, headers=headers, params=params)
            if response.status_code != 200:
                print(f"/{endpoint_url} API call failed with status code: {response.status_code}.")
                print(response.text)
                print(f"Failed request URL and params: {response.request.url}")
                break

            items_data = response.json().get('items')
            items += items_data
            if not response.json().get('has_more'):
                break

            # If the endpoint gets overloaded, it will send a backoff request in the response
            # Failure to backoff will result in a 502 Error
            if response.json().get('backoff'):
                print("Backoff request received from endpoint. Waiting 15 seconds...")
                time.sleep(15)
            params['page'] += 1

        return items


def get_users(base_url, client):

    s = create_session(base_url)
    users = client.get_all_users()

    ### REMOVE THIS LINE WHEN DONE TESTING ###
    users = [user for user in users if user['user_id'] > 28000]

    no_org_count = 0
    start_time = time.time()
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
    
    end_time = time.time()
    elapsed_time = end_time - start_time

    # 116 seconds to get 531 users on SO Business (0.218 seconds per user)
    # 8332 seconds (2.33 hours) to get 20493 users on SO Enterprise (0.407 seconds per user)
    print('*************************************************************************************')
    print(f"It took {elapsed_time} seconds to get info for {len(users)} users")
    print(f"{no_org_count} users had no documented organization")
    print('*************************************************************************************')
    
    return users


def create_session(base_url):

    options = webdriver.ChromeOptions()
    options.add_argument("--window-size=500,800")
    options.add_experimental_option("excludeSwitches", ['enable-automation'])
    driver = webdriver.Chrome(options=options)
    driver.get(base_url)

    # Test again now that I fixed the find_element problem
    while True:
        try:
            # element names for selenium: https://selenium-python.readthedocs.io/locating-elements.html
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

# Need to split this into smaller functions
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
    
    file_path = os.path.join('data', 'interaction_matrix.csv')
    interaction_matrix.to_csv(file_path)

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
def get_scim_users(scim_token):

    site_url = "https://soedemo.stackenterprise.co"
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


# TODO
# Next steps:
    # Set url and apikey via command line arguments (do this for tag metrics too)

    # Tell the user they're going to get prompted to login (hit any key to continue)
        # and that the window will close automatically when they're done
    # What % of interactions happen within a department vs. across departments?
    # What % of interactions are untracked?
    # Should we track how many people are generating the interactions? (i.e. how many people are asking questions vs. answering questions)
    # If breaking create_interaction_data() into multiple functions, it fixes the answer comment issue

# Parking lot:
    # instead of marking untracked interactions, mark the user as "deleted" and org as "unspecified"
    # split out interacting users and orgs into answering and commenting
    # ability to turn off comment tracking
    # when the owner of a question/answer is deleted, ALL interactions are counted as untracked
        # However, validating the user IDs of answers/comments might discover that many of these 
        # interactions shouldn't be tracked anyway, thus inflating the number

# SO Internal Baselines:
    # interaction_count = 3012 (5254 with comments) -- 57% increase
    # untracked interactions = 7724 (8583 with comments)
    # questions_count = 8481
    # answers_count = 9824
    # comments_count = 12797
        # 0.7 comments per question/answer
        # Interations increased by 2242, which is 17.6% of the total comments 