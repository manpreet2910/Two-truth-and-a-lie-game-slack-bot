import os
from dotenv import load_dotenv
import slack
from flask import Flask, request, Response
from slackeventsapi import SlackEventAdapter
import time
import random

load_dotenv()

app = Flask(__name__)
slack_event_adapter = SlackEventAdapter(os.environ['SIGNING_SECRET'], '/slack/events', app)
slack_token = os.environ['SLACK_TOKEN']
client = slack.WebClient(token=slack_token)
BOT_ID = client.api_call("auth.test")['user_id']
user_games = {}

def post_message(channel, text, blocks=None):
    if blocks:
        client.chat_postMessage(channel=channel, text=text, blocks=blocks)
    else:
        client.chat_postMessage(channel=channel, text=text)

@slack_event_adapter.on('team_join')
def on_team_join(payload):
    event = payload.get('event', {})
    user_id = event.get('user', {}).get('id', None)
    if user_id:
        channel_id = event.get('user', {}).get('id', None)
        ask_play_game(channel_id)

@slack_event_adapter.on('member_joined_channel')
def on_member_joined_channel(payload):
    print(payload)  # Print payload for debugging
    event = payload.get('event', {})
    user_id = event.get('user', None)
    channel_id = event.get('channel', None)
    if user_id and channel_id:
        ask_play_game(channel_id)  

def ask_play_game(channel_id):
    message_text = "Welcome! Would you like to play a game of Two Truths and a Lie?"
    message_blocks = [
        {
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": message_text
            },
            "accessory": {
                "type": "actions",
                "elements": [
                    {
                        "type": "button",
                        "text": {
                            "type": "plain_text",
                            "text": "Yes",
                            "emoji": True
                        },
                        "value": "play_game",
                        "action_id": "play_game"
                    },
                    {
                        "type": "button",
                        "text": {
                            "type": "plain_text",
                            "text": "No",
                            "emoji": True
                        },
                        "value": "not_play_game",
                        "action_id": "not_play_game"
                    }
                ]
            }
        }
    ]
    post_message(channel_id, None, blocks=message_blocks)

@app.route('/slack/message_actions', methods=['POST'])
def message_actions():
    payload = request.form.to_dict()
    if payload['type'] == 'block_actions':
        user_id = payload['user']['id']
        selected_option = payload['actions'][0]['value']
        if selected_option == 'play_game':
            initiate_game(user_id)
        elif selected_option == 'not_play_game':
            post_message(user_id, "No problem! Feel free to join the game anytime.")
    return Response(), 200

def initiate_game(user_id):
    post_message(user_id, "Great! Let's start the game. Please tell me two truths about yourself and one lie.")

@slack_event_adapter.on('message')
def on_message(payload):
    event = payload.get('event', {})
    user_id = event.get('user', None)
    text = event.get('text', '')
    if user_id != BOT_ID:
        if user_id in user_games:
            handle_game_response(user_id, text)
        else:
            try:
                guess = int(text)
                for user, data in user_games.items():
                    if 'lie' in data:
                        data['guess'] = data['truths'][guess - 1]
            except ValueError:
                pass

def handle_game_response(user_id, text):
    if user_id in user_games:
        user_data = user_games[user_id]
        if 'truths' not in user_data:
            user_data['truths'] = []
        user_data['truths'].append(text.strip())
        if len(user_data['truths']) == 2:
            post_message(user_id, "Great! Now please tell me your lie.")
        elif len(user_data['truths']) == 3:
            user_games.pop(user_id)
            user_data['lie'] = user_data['truths'].pop(random.randint(0, 2))
            announce_game(user_id, user_data['truths'])
            time.sleep(60)  # Wait for 1 minute
            reveal_lie(user_id, user_data['lie'])

def announce_game(user_id, truths):
    message = f"User <@{user_id}> has provided the following two truths:\n\n"
    for i, truth in enumerate(truths, start=1):
        message += f"{i}. {truth}\n"
    message += "\nCan you guess which one is the lie? Reply with the number of the statement you think is the lie."
    post_message('#s_bot', message)

def reveal_lie(user_id, lie):
    guesses = {}
    for user, data in user_games.items():
        if 'guess' in data:
            guesses[user] = data['guess']

    correct_guesses = [user for user, guess in guesses.items() if guess == lie]
    incorrect_guesses = [user for user, guess in guesses.items() if guess != lie]

    result_message = f"The lie from <@{user_id}> was:\n\n{lie}\n\n"
    if correct_guesses:
        result_message += "Correct guesses:\n"
        for user in correct_guesses:
            result_message += f"<@{user}>\n"
    if incorrect_guesses:
        result_message += "\nIncorrect guesses:\n"
        for user in incorrect_guesses:
            result_message += f"<@{user}>\n"

    post_message('#s_bot', result_message)
    for user in guesses:
        user_games.pop(user, None)

if __name__ == '__main__':
    app.run(debug=True)