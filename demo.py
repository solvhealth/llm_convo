from gevent import monkey
from dotenv import load_dotenv
import os

load_dotenv()

monkey.patch_all()

from llm_convo.agents import OpenAIChat, TwilioCaller
from llm_convo.twilio_io import TwilioServer
from llm_convo.conversation import run_conversation
import logging
import time

logging.getLogger().setLevel(logging.INFO)

tws = TwilioServer(
    remote_host="f1eb-2603-8000-d100-14c9-4540-268c-5e7a-d53d.ngrok-free.app",
    port=8080,
    # written correctly
    static_dir=r"static",
)
# Point twilio voice webhook to https://abcdef.ngrok.app/audio/incoming-voice
tws.start()

# agent_a = OpenAIChat(
#     system_prompt="You are a Haiku Assistant. Answer whatever the user wants but always in a rhyming Haiku.",
#     init_phrase="This is Haiku Bot, how can I help you.",
# )
# agent_a = OpenAIChat(
#     system_prompt="""
#         You are an ordering bot that is going to call a pizza place an order a pizza.
#         When you need to say numbers space them out (e.g. 1 2 3) and do not respond with abbreviations.
#         If they ask for information not known, make something up that's reasonable.

#         The customer's details are:
#         * Address: 1234 Candyland Road, Apt 506
#         * Credit Card: 1234 5555 8888 9999 (CVV: 010)
#         * Name: Bob Joe
#         * Order: 1 large pizza with only pepperoni
#         """,
#     init_phrase="Hi, I would like to order a pizza.",
# )

agent_a = OpenAIChat(
    system_prompt="""
        You are an expert voice assistant making an urgent care appointment on behalf of a patient.
        He would like an appointment time between 2pm and 4pm today. 
        Be courteous and professional. If they ask for insurance or other personal information, do not provide it or try to fill it in.
        If those times are not availble, end the conversation. If you confirm a time, "Thank you, appointment confirmed. Goodbye."
        """,
    init_phrase="Hello, I'm a digital voice assistant calling on behalf of Mitchell Rivet. He would like an appointment between 2 and 4pm. Do you have availability?",
)


def run_chat(sess):
    print("running chat", sess)
    agent_b = TwilioCaller(sess)
    while not agent_b.session.media_stream_connected():
        time.sleep(0.1)
    run_conversation(agent_a, agent_b)


tws.on_session = run_chat

# You can also have ChatGPT actually start the call, e.g. for automated ordering
# mitch's phone number fyi
tws.start_call("+15035761174")
