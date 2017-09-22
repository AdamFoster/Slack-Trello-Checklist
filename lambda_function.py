import boto3
import json
import urllib
import os
import requests
from base64 import b64decode

ENCRYPTED_SLACK_TOKEN = os.environ['SLACK_TOKEN']
SLACK_TOKEN = boto3.client('kms').decrypt(CiphertextBlob=b64decode(ENCRYPTED_SLACK_TOKEN))['Plaintext'].decode()
ENCRYPTED_TRELLO_KEY = os.environ['TRELLO_KEY']
TRELLO_KEY = boto3.client('kms').decrypt(CiphertextBlob=b64decode(ENCRYPTED_TRELLO_KEY))['Plaintext'].decode()
ENCRYPTED_TRELLO_TOKEN = os.environ['TRELLO_TOKEN']
TRELLO_TOKEN = boto3.client('kms').decrypt(CiphertextBlob=b64decode(ENCRYPTED_TRELLO_TOKEN))['Plaintext'].decode()

CHEKCLIST_GET_URL = 'https://api.trello.com/1/checklists/{checklist_id}?fields=name&cards=open&card_fields=name&key={application_key}&token={auth_token}'
CHECKLIST_PUT_URL = 'https://api.trello.com/1/cards/{card_id}/checkItem/{item_id}?key={application_key}&token={auth_token}&state={state}'
CHECKLIST_POST_URL = 'https://api.trello.com/1/checklists/{checklist_id}/checkItems?name={text}&pos=bottom&checked=false&key={application_key}&token={auth_token}'

CARD_ID = os.environ['CARD_ID']
CHECKLIST_ID = os.environ['CHECKLIST_ID']

SSL_VERIFY = True

CALLBACK_ID_CHECK = 'shop_check'
CALLBACK_ID_UNCHECK = 'shop_uncheck'


print('Loading shop function')
dynamo = boto3.client('dynamodb')

def lambda_response(status_code):
    return {
        "isBase64Encoded": False,
        "statusCode": status_code,
        "headers": {  },
        "body": ""
    }

def respond_async(url, response):
    resp = requests.post(url, json=response)
    if resp.status_code == requests.codes.ok:
        print('Successful post-back')
    else:
        print('HTTP ' + str(resp.status_code) + ' when posting back')
        print(resp.text)

def respond_ephemeral(url, text):
    respond_async(url, {
        "response_type": "ephemeral",
        "text": text,
        "mrkdwn": True
    })

def respond_in_channel(url, text):
    respond_async(url, {
        "response_type": "in_channel",
        "text": text,
        "mrkdwn": True
    })

def display_instructions(url):
    response = {
        "response_type": "ephemeral",
        "text": "Shopping list usage guide",
        "mrkdwn": True,
        "attachments": [
            {
                "text": "To view the list use '/shop list [all]'\nTo add an item use '/shop add <item>'\nTo mark an item use '/shop mark <item>'"
            }
        ]
    }
    respond_async(url, response)


def update_item(item_id, state):
    resp = requests.put(CHECKLIST_PUT_URL.format(card_id=CARD_ID, checklist_id=CHECKLIST_ID, 
            item_id=item_id, application_key=TRELLO_KEY, auth_token=TRELLO_TOKEN, state=state), 
            verify=SSL_VERIFY)
    #print(resp.request.url)
    if resp.status_code != requests.codes.ok:
        print('HTTP ' + str(resp.status_code) + ' when updating checklist item ' + item_id)
        print(resp.text)
        return False
    else:
        return True

def uncomplete_item(item_id):
    return update_item(item_id, 'incomplete')

def complete_item(item_id):
    return update_item(item_id, 'complete')

def get_candidates(text, state):
    resp = requests.get(CHEKCLIST_GET_URL.format(checklist_id=CHECKLIST_ID, application_key=TRELLO_KEY, 
            auth_token=TRELLO_TOKEN), verify=SSL_VERIFY)
    candidates = []
    if resp.status_code == requests.codes.ok:
        checklist = resp.json()
        sorted_list = sorted(checklist['checkItems'], key=lambda k: k['pos'])
        #print("Items found: " + json.dumps(sorted_list, indent=2))
        for item in sorted_list:
            if item['state'] == state:
                candidate = {}
                candidate['name'] = item['name']
                candidate['id'] = item['id']
                candidate['rating'] = 1 if (text in candidate['name'].lower()) else 0
                if candidate['rating'] == 1:
                    candidates.append(candidate)
        return candidates        
    else:
        print('HTTP ' + str(resp.status_code) + ' when getting checklist for marking')
        print(resp.text)
        respond_ephemeral(slack_response_url, "Error code when asking Trello")
        return None

def lambda_handler(event, context):
    '''Shopping list stored in Trello
    '''
    #print("Received event: " + json.dumps(event, indent=2))
    
    body = urllib.parse.parse_qs(event['body'])
    #print("Body is: " + json.dumps(body, indent=2))
    
    if 'payload' in body:
        ### interactive message
        #print("Payload: " + body['payload'][0])
        payload = json.loads(body['payload'][0])
        if SLACK_TOKEN != payload['token']:
            print("Invalid token: " + SLACK_TOKEN + " vs " + payload['token'])
        slack_response_url = payload['response_url']
        check_item_id = payload['actions'][0]['value']
        check_item_name = payload['actions'][0]['name']
        callback_id = payload['callback_id']
        if callback_id == CALLBACK_ID_CHECK:
            print('Completing item ' + check_item_id)
            if complete_item(check_item_id):
                respond_in_channel(slack_response_url, "<@{user}> checked *{text}* off the list".format(user=payload['user']['id'], text=check_item_name))
            else:
                respond_ephemeral(slack_response_url, "Unable to complete item: " + check_item_name)
        elif callback_id == CALLBACK_ID_UNCHECK:
            print('Uncompleting item ' + check_item_id)
            if uncomplete_item(check_item_id):
                respond_in_channel(slack_response_url, "<@{user}> unchecked *{text}* on the list".format(user=payload['user']['id'], text=check_item_name))
            else:
                respond_ephemeral(slack_response_url, "Unable to complete item: " + check_item_name)
        else:
            print('Unknown callback id: ' + callback_id)

        return lambda_response(200)
        

    if SLACK_TOKEN != body['token'][0]:
        print("Invalid token: " + SLACK_TOKEN + " vs " + body['token'][0])
    slack_response_url = body['response_url'][0]
    print("slack_response_url: " + slack_response_url)

    if 'text' in body:
        text = body['text'][0]
        user = body['user_id'][0]
        
        if text.startswith('add '):
            text = text[3:].strip()
            if len(text) > 0:
                ### Add text to list
                resp = requests.post(CHECKLIST_POST_URL.format(checklist_id=CHECKLIST_ID, application_key=TRELLO_KEY, 
                        auth_token=TRELLO_TOKEN, text=text), verify=SSL_VERIFY)
                if resp.status_code == requests.codes.ok:
                    respond_in_channel(slack_response_url, "<@{user}> added *{text}* to the shopping list".format(user=user, text=text))
                else:
                    print('HTTP ' + str(resp.status_code) + ' when getting checklist')
                    print(resp.text)
                    respond_ephemeral(slack_response_url, "Couldn't add to shopping list")
            else:
                display_instructions(slack_response_url)


        elif text.startswith('check ') or text.startswith('mark '):
            text = text[5:].strip().lower()
            if len(text) > 0:
                candidates = get_candidates(text, 'incomplete')
                if candidates is None:
                    pass
                elif len(candidates) == 0:
                    respond_ephemeral(slack_response_url, "No match found. Please enter a substring, e.g. to mark 'Pasta' you can use '/shop mark pas") 
                elif len(candidates) > 3:
                    respond_ephemeral(slack_response_url, "Too many matches found. Please try a longer substring, e.g. to mark 'Pasta' you can use '/shop mark pas") 
                elif len(candidates) == 1:
                    if complete_item(candidates[0]['id']):
                        respond_in_channel(slack_response_url, "<@{user}> checked *{text}* off the list".format(user=user, text=candidates[0]['name'])) 
                    else:
                        respond_ephemeral(slack_response_url, "Error updating item") 
                else:
                    #2-3 candidates
                    actions = [{"name":x['name'], "text":x['name'], "type":"button", "value":x['id']} for x in candidates]
                    respond_async(slack_response_url, {
                        "response_type": "ephemeral",
                        "text": "Be specific, be, be, specific",
                        "mrkdwn": True,
                        "attachments": [
                            {
                                "text": "Choose an item to mark",
                                "callback_id": CALLBACK_ID_CHECK,
                                "attachment_type": "default",
                                "actions": actions
                            }
                        ]
                    }) 
            else:
                respond_ephemeral(slack_response_url, "Enter an item (or part of an item) to mark. e.g. to mark 'Pasta' you can use '/shop mark pas") 


        elif text.startswith('uncheck ') or text.startswith('unmark '):
            text = text[7:].strip().lower()
            if len(text) > 0:
                candidates = get_candidates(text, 'complete')
                if candidates is None:
                    pass
                elif len(candidates) == 0:
                    respond_ephemeral(slack_response_url, "No match found. Please enter a substring, e.g. to unmark 'Pasta' you can use '/shop unmark pas") 
                elif len(candidates) > 3:
                    respond_ephemeral(slack_response_url, "Too many matches found. Please try a longer substring, e.g. to unmark 'Pasta' you can use '/shop unmark pas") 
                elif len(candidates) == 1:
                    if uncomplete_item(candidates[0]['id']):
                        respond_in_channel(slack_response_url, "<@{user}> unchecked *{text}* on the list".format(user=user, text=candidates[0]['name'])) 
                    else:
                        respond_ephemeral(slack_response_url, "Error updating item") 
                else:
                    #2-3 candidates
                    actions = [{"name":x['name'], "text":x['name'], "type":"button", "value":x['id']} for x in candidates]
                    respond_async(slack_response_url, {
                        "response_type": "ephemeral",
                        "text": "Be specific, be, be, specific",
                        "mrkdwn": True,
                        "attachments": [
                            {
                                "text": "Choose an item to unmark",
                                "callback_id": CALLBACK_ID_UNCHECK,
                                "attachment_type": "default",
                                "actions": actions
                            }
                        ]
                    }) 
            else:
                respond_ephemeral(slack_response_url, "Enter an item (or part of an item) to unmark. e.g. to unmark 'Pasta' you can use '/shop unmark pas") 


        elif text == 'list' or text == 'list all' or text == 'listall':
            ### display shopping list
            show_all = True
            if text == 'list':
                show_all = False
            resp = requests.get(CHEKCLIST_GET_URL.format(checklist_id=CHECKLIST_ID, application_key=TRELLO_KEY, 
                    auth_token=TRELLO_TOKEN), verify=SSL_VERIFY)
            if resp.status_code == requests.codes.ok:
                checklist = resp.json()
                #print(checklist)
                items = []
                count = 0
                sorted_list = sorted(checklist['checkItems'], key=lambda k: k['pos']) 
                for item in sorted_list:
                    if item['state'] == 'incomplete':
                        #print(item['id'] + ' = ' + item['name'])
                        items.append(item['name'])
                        count = count + 1
                    else:
                        if show_all:
                            items.append('~' + item['name'] + '~')
                respond_ephemeral(slack_response_url, "Shopping for {num} items\n".format(num=count) + "\n".join(items))
            
            else:
                print('HTTP ' + str(resp.status_code) + ' when getting checklist')
                print(resp.text)
                respond_ephemeral(slack_response_url, "Error when asking Trello")
        else:
            display_instructions(slack_response_url)
    else:
        display_instructions(slack_response_url)

    return lambda_response(200)