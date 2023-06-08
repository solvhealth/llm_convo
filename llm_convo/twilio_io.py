import threading
import logging
import os
import base64
import json
import time

from gevent.pywsgi import WSGIServer
from twilio.rest import Client
from twilio.twiml.voice_response import VoiceResponse, Start
from flask import Flask, Response, send_from_directory, render_template
from flask_sock import Sock
import simple_websocket
import audioop

from llm_convo.audio_input import WhisperTwilioStream


# TODO: remote host here?
XML_MEDIA_STREAM = """
<Response>
    <Start>
        <Stream name="Audio Stream" url="wss://{host}/audiostream" />
    </Start>
</Response>
"""

MATCHING_TWILIO = """
<?xml version="1.0" encoding="UTF-8"?>
    <Response>
        <Say>Hello, Trevor, it's good to hear from you.</Say>
    </Response>
"""

TEST_AUDIO = """
<?xml version="1.0" encoding="UTF-8"?>
<Response>
  <Say>Hello!</Say>
    <Start>
        <Stream name="Audio Stream" url="wss://{host}/audiostream" />
    </Start>
</Response>
"""

# <Pause length="60"/>


class TwilioServer:
    def __init__(self, remote_host: str, port: int, static_dir: str):
        self.app = Flask(__name__)
        self.sock = Sock(self.app)
        self.remote_host = remote_host
        self.port = port
        # BUG: the path here was off initially
        self.static_dir = static_dir
        self.server_thread = threading.Thread(target=self._start)
        self.on_session = None

        account_sid = os.environ["TWILIO_ACCOUNT_SID"]
        self.from_phone = os.environ["TWILIO_PHONE_NUMBER"]
        api_key = os.environ["TWILIO_API_KEY"]  # might just be SID
        api_secret = os.environ["TWILIO_API_SECRET"]  # dami gave
        account_sid = os.environ["TWILIO_ACCOUNT_SID"]  # test from twilio
        self.client = Client(api_key, api_secret, account_sid)

        @self.app.route("/audio/<key>")
        def audio(key):
            audio_path = self.static_dir + "/" + str(int(key)) + ".mp3"
            # had to update to read correctly
            return send_from_directory("../" + self.static_dir, str(int(key)) + ".mp3")

        @self.app.route("/test")
        def test():
            return "hello world"

        @self.app.route("/audio/incoming-voice", methods=["POST"])
        def incoming_voice():
            logging.info("Incoming call")
            twiml_response = VoiceResponse()

            start = Start()
            start.stream(
                name="Example Audio Stream", url=f"wss://{self.remote_host}/audiostream"
            )
            twiml_response.append(start)

            return Response(str(twiml_response), mimetype="application/xml")

        @self.sock.route("/audiostream", websocket=True)
        def on_media_stream(ws):
            logging.info("Media stream connected")
            session = TwilioCallSession(
                ws,
                self.client,
                remote_host=self.remote_host,
                static_dir=self.static_dir,
            )
            if self.on_session is not None:
                thread = threading.Thread(target=self.on_session, args=(session,))
                thread.start()
            session.start_session()

    def start_call(self, to_phone: str):
        # NOTE: still having issues passing in plain twiml...
        # this should work, and would be easier to dev with.
        # however, I've just defaulted to using the hosted twiml bin through the twilio console for now
        # twiml_string = f'<Response><Say>Hello!</Say><Start><Stream name="Audio Stream" url="wss://{self.remote_host}/audiostream" /></Start></Response>'
        self.client.calls.create(
            # twiml=twiml_string,
            url="https://handler.twilio.com/twiml/EHd5240a6bfa49988135723404c8bef70c",
            to=to_phone,
            from_=self.from_phone,
        )

    def _start(self):
        logging.info("Starting Twilio Server")
        WSGIServer(("0.0.0.0", self.port), self.app).serve_forever()

    def start(self):
        self.server_thread.start()


class TwilioCallSession:
    def __init__(self, ws, client: Client, remote_host: str, static_dir: str):
        self.ws = ws
        self.client = client
        self.sst_stream = WhisperTwilioStream()
        self.remote_host = remote_host
        self.static_dir = static_dir
        self._call = None

    def media_stream_connected(self):
        return self._call is not None

    def _read_ws(self):
        while True:
            try:
                message = self.ws.receive()
            except simple_websocket.ws.ConnectionClosed:
                logging.warn("Call media stream connection lost.")
                break
            if message is None:
                logging.warn("Call media stream closed.")
                break

            data = json.loads(message)
            if data["event"] == "start":
                logging.info("Call connected, " + str(data["start"]))
                self._call = self.client.calls(data["start"]["callSid"])
            elif data["event"] == "media":
                media = data["media"]
                chunk = base64.b64decode(media["payload"])
                if self.sst_stream.stream is not None:
                    self.sst_stream.stream.write(audioop.ulaw2lin(chunk, 2))
            elif data["event"] == "stop":
                logging.info("Call media stream ended.")
                break

    def get_audio_fn_and_key(self, text: str):
        key = str(abs(hash(text)))
        path = os.path.join(self.static_dir, key + ".mp3")
        return key, path

    def play(self, audio_key: str, duration: float):
        play_audio = f'<Response><Play>https://{self.remote_host}/audio/{audio_key}</Play><Pause length="60"/></Response>'

        self._call.update(twiml=play_audio)
        time.sleep(duration + 0.2)

    def start_session(self):
        self._read_ws()
