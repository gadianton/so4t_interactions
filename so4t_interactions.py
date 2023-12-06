'''
This Python script is offered with no formal support. 
If you run into difficulties, reach out to the person who provided you with this script.
'''

# Standard library imports
import argparse
import json
import os

# Third-party library imports
import pandas as pd
from d3blocks import D3Blocks

# Local libraries
from so4t_api_v2 import V2Client
from so4t_api_v3 import V3Client


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
                '--key "YOUR_KEY --token "YOUR_TOKEN" \n\n')
    parser.add_argument('--url', 
                        type=str, 
                        help='[REQUIRED] Base URL for Stack Overflow for Teams site')
    parser.add_argument('--token',
                        type=str,
                        help='[REQUIRED] API token')
    parser.add_argument('--key',
                        type=str,
                        help='API key. Only required for Stack Overflow Enterprise sites')
    parser.add_argument('--team-rename',
                        type=str,
                        help='CSV file containing changes to team names. Not to be used with '
                        '--remove-team-numbers')
    parser.add_argument('--remove-team-numbers',
                        action='store_true',
                        help='Remove team numbers from team names. Not to be used with '
                        '--team-rename')

    return parser.parse_args()


def data_collector(args):

    # Create API clients
    v2client = V2Client(args)
    v3client = V3Client(args)

    # Get user data
    if args.team_rename:
        team_rename = pd.read_csv(args.team_rename)
        team_rename = team_rename.set_index('old_team_name').to_dict()['new_team_name']
        users = get_user_data(v3client, team_rename=team_rename)
    elif args.remove_team_numbers:
        users = get_user_data(v3client, team_numbers=False)
    else: # if no team rename file is provided
        users = get_user_data(v3client)

    # Get question data
    questions = get_question_data(v2client)

    return users, questions


def get_user_data(client, team_rename=None, team_numbers=True):

    users = client.get_all_users()

    # Exclude users with an ID of less than 1 (i.e. Community user and user groups)
    users = [user for user in users if user['id'] > 1]

    if 'soedemo' in client.api_url: # for internal testing environment
        users = [user for user in users if user['id'] > 28000]

    if team_rename:
        for user in users:
            try:
                user['department'] = team_rename[user['department']]
            except KeyError:
                pass
    elif team_numbers:
        # Remove team numbers from the end of team names
        # Examples: PM63 -> PM, Engineering 2.1 -> Engineering
        for user in users:
            try:
                while not user['department'][-1].isalpha():
                    user['department'] = user['department'][:-1]
            except TypeError: # if user['department'] is None
                pass

    export_to_json('users', users)

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


def data_processor(users, questions):

    interaction_data, untracked_interactions = create_interaction_data(questions, users, questions)
    print(f"Number of interactions not tracked due to deleted users: {untracked_interactions}")
    export_to_json('interaction_data', interaction_data)

    interaction_matrix = create_interaction_matrix(interaction_data)

    return interaction_matrix


# Should split this into smaller functions
def create_interaction_data(content_list, users, questions):

    interaction_data = []
    untracked_interactions = 0

    for content in content_list:
        interaction = {
            'source_user': validate_user_id(content['owner']),
            'source_team': None,
            'interacting_users': [],
            'interacting_teams': [],
            'post_type': None,
            'id': None,
            'tags': None # only for questions
        }
        interaction['source_team'] = find_user_team(interaction['source_user'], users)

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
                interaction, untracked_interactions = add_user_and_team(
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
                interaction, untracked_interactions = add_user_and_team(
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
    # Since this user data is from API v2, it uses a 'user_id' key instead of 'id'

    try:
        return user['user_id']
    except KeyError:
        return None
    

def find_user_team(user_id, users):
    # Since `users` is from API v3, it uses an 'id' key instead of 'user_id'

    search_result = next((item for item in users if int(item['id']) == user_id), None)
    try:
        user_team = search_result['department']
    except TypeError: # if None is returned from the search_result
        user_team = search_result
    
    return user_team


def find_original_question(question_id, questions):

    search_result = next((item for item in questions if int(item['question_id']) == question_id), None)
    
    return search_result


def add_user_and_team(interaction, content, untracked_interactions, users):

    source_user = interaction['source_user']
    interacting_users = interaction['interacting_users']
    new_user = validate_user_id(content['owner'])

    if not new_user: # if the user has been deleted
        untracked_interactions += 1
    else:
        if new_user != source_user and new_user not in interacting_users:
            interaction['interacting_users'].append(new_user)
            interacting_team = find_user_team(new_user, users)
            if not interacting_team: # unable to properly track interaction if there is no team
                untracked_interactions += 1
            elif interacting_team not in interaction['interacting_teams']:
                interaction['interacting_teams'].append(find_user_team(new_user, users))

    return interaction, untracked_interactions


def create_interaction_matrix(interaction_data):

    matrix_data = []
    for interaction in interaction_data:
        if interaction['post_type'] == 'question': # if it's a question
            source_team = interaction['source_team']
        else: # if it's an answer
            target_team = interaction['source_team']
        
        for team in interaction['interacting_teams']:
            if source_team: # if it's a question
                matrix_data.append({
                    'source': source_team,
                    'target': team
                })
            else: # if it's an answer
                matrix_data.append({
                    'source': team,
                    'target': target_team
                })
    
    # create and format dataframe
    interaction_matrix = pd.DataFrame(matrix_data).groupby(['source', 'target']).size()
    interaction_matrix = interaction_matrix.reset_index(name='weight')
    interaction_matrix = interaction_matrix.pivot(
        index='source', columns='target', values='weight').fillna(0)
    interaction_matrix = interaction_matrix.astype(int)
    
    # export interaction matrix to csv
    file_name = 'interaction_matrix.csv'
    interaction_matrix.to_csv(file_name)
    print(f"'{file_name}' has been created in the current working directory.")

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
                    notebook=False,
                    save_button=False)

    # change size and position of the svg
    modified_html = original_html.replace('-width / 2, -height / 2, width, height',
                                          'width - 1400, height - 1425, width + 200, height + 200')
    with open(filepath, 'w') as f:
        f.write(modified_html)

    print("Chord diagram created. You can find it in the current working directory.")


def export_to_json(data_name, data):

    file_name = f"{data_name}.json"

    with open(file_name, 'w') as f:
        json.dump(data, f, indent=4)

    print(f"'{file_name}' has been created in the current working directory.")


if __name__ == '__main__':

    main()
