# Slack-Trello-Checklist
Manages my shopping list in Trello using Slack via AWS Lambda

## Install "guide"
Create a Lambda function using Python 3.6 (using API gateway - no auth)

Add the following variables: 
* CHECKLIST_ID
* CARD_ID
* SLACK_TOKEN (encrypted)
* TRELLO_TOKEN (encrypted)
( TRELLO_KEY (encrypted)

Create a zip file including the lambda_function.py and request module

Upload to the lambda function

Add the gateway URL to Slack as an application with Interactive Messages and Slash Commands
