import os.path
import datetime
import requests
import random
import re
from datetime import datetime, timedelta
import threading
import wave
import struct
import time
import base64
import pyaudio
import pvporcupine
import speech_recognition as sr
from gtts import gTTS
import tempfile
import re
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
import spotipy
from spotipy.oauth2 import SpotifyOAuth
import nltk
from nltk.tokenize import word_tokenize
from fractions import Fraction
from word2number import w2n
import geocoder
from dotenv import load_dotenv
load_dotenv(dotenv_path='./apiKeys.env')
nltk.download('punkt')

# Gloabal variable for managing states
stop_speaking = False


# Gmail API scopes
SCOPES = [
    'https://www.googleapis.com/auth/gmail.send',
    'https://www.googleapis.com/auth/gmail.readonly',
    'https://www.googleapis.com/auth/calendar'
]

def google_api_init(api_service_name, api_version):
    creds = None
    if os.path.exists("token.json"):
        creds = Credentials.from_authorized_user_file("token.json", SCOPES)
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file(os.getenv('GOOGLE_CLIENT_SECRETS_JSON'), SCOPES)
            creds = flow.run_local_server(port=8080)
        with open("token.json", "w") as token:
            token.write(creds.to_json())
    return build(api_service_name, api_version, credentials=creds)

def auth_spotify(client_id, client_secret, redirect_uri, scope):
    # Initialize Spotify OAuth
    oauth_object = SpotifyOAuth(
        client_id=client_id,
        client_secret=client_secret,
        redirect_uri=redirect_uri,
        scope=scope
    )

    # Try to get a valid token for the session, refreshing if necessary
    token_info = oauth_object.get_cached_token()

    if token_info:
        print("Found cached token!")
    else:
        # No valid token available, need to log in
        auth_url = oauth_object.get_authorize_url()
        print(f"Please go to this URL and authorize: {auth_url}")

        # Manual step: user must go to URL and then paste redirected URL here
        response_url = input("Enter the URL you were redirected to: ")
        code = oauth_object.parse_response_code(response_url)
        token_info = oauth_object.get_access_token(code)

    # Create a Spotify client with the access token
    spotify_client = spotipy.Spotify(auth=token_info['access_token'])

    return spotify_client

def Initialize_porcupine():
    # Porcupine is used for the wake words
    access_key = os.getenv('PORCUPINE_ACCESS_KEY')
    keyword_paths = os.getenv('PORCUPINE_KEYWORD_PATHS')

    if not access_key or not keyword_paths:
        print("Porcupine access key or keyword paths are not set")
        raise EnvironmentError("Missing required environment variables")
    
    keyword_paths_list = keyword_paths.split(';')

    # change line below to change which wake word is used
    porcupine = pvporcupine.create(access_key=access_key, keyword_paths=keyword_paths_list)
    
    pa = pyaudio.PyAudio()
    audio_stream = pa.open(
        rate=porcupine.sample_rate,
        channels=1,
        format=pyaudio.paInt16,
        input=True,
        frames_per_buffer=porcupine.frame_length
    )
    return porcupine, pa, audio_stream

def stop_functions():
    global stop_speaking
    stop_speaking = True

def threaded_speak(text):
    thread = threading.Thread(target=speak, args=(text,))
    thread.start()

def speak(text):
    global stop_speaking
    if stop_speaking:
        return
    try:
        # Create a temporary file
        temp_fd, temp_path = tempfile.mkstemp(suffix='.mp3')
        os.close(temp_fd)  # Close the file descriptor

        # Create TTS object and save the speech file
        tts = gTTS(text=text, lang='en')
        tts.save(temp_path)

        # Play the speech file (modify command according to your OS)
        os.system(f'start {temp_path}')
        
        # Wait for a few seconds to ensure file is played
        time.sleep(3)
    except Exception as e:
        print(f"Error in speak function: {e}")
    finally:
        # Delete the temporary file
        if os.path.exists(temp_path):
            os.remove(temp_path)

def extract_time_from_command(command):
    # Regular expressions to extract time
    timer_regex = r"set a timer for (\d+) (seconds|minutes|hours|second|minute|hour)"
    alarm_regex = r"set an alarm for (\d+:\d+\s*(a\.m\.|p\.m\.))"

    # Check for timer
    command = command.lower()
    timer_match = re.search(timer_regex, command)
    if timer_match:
        duration, unit = timer_match.groups()
        return "timer", int(duration), unit

    # Check for alarm
    alarm_match = re.search(alarm_regex, command)
    if alarm_match:
        time_str = alarm_match.group(1)
        # Replace 'a.m.' with 'AM' and 'p.m.' with 'PM'
        time_str = time_str.replace('a.m.', 'AM').replace('p.m.', 'PM')
        return "alarm", datetime.strptime(time_str, "%I:%M %p"), None

    return None, None, None

def set_timer(duration, unit):
    total_seconds = duration
    if unit == "minutes":
        total_seconds *= 60
    elif unit == "hours":
        total_seconds *= 3600
    threading.Timer(total_seconds, timer_finished).start()
    print(f"Timer set for {duration} {unit}")

def set_alarm(alarm_time):
    now = datetime.now()

    if isinstance(alarm_time, datetime):
        # Extract only the time part and combine it with today's date
        alarm_time = datetime.combine(now.date(), alarm_time.time())
    else:
        # If alarm_time is not a datetime object, handle accordingly
        # (e.g., if it's a time object, combine it with today's date)
        alarm_time = datetime.combine(now.date(), alarm_time)

    # If the alarm time is before the current time, set it for the next day
    if alarm_time < now:
        alarm_time += timedelta(days=1)
    print(alarm_time)
    wait_seconds = (alarm_time - now).total_seconds()
    threading.Timer(wait_seconds, alarm_finished).start()
    print(f"Alarm set for {alarm_time.strftime('%I:%M %p')}")

def play_wav(filename):
    global stop_speaking

    wf = wave.open(filename, 'rb')
    p = pyaudio.PyAudio()

    # Open a stream
    stream = p.open(format=p.get_format_from_width(wf.getsampwidth()),
                    channels=wf.getnchannels(),
                    rate=wf.getframerate(),
                    output=True)

    # Read data in chunks
    chunk_size = 1024
    data = wf.readframes(chunk_size)

    # Play the stream
    while data != b'':
        # Check for stop_speaking state if true it stops
        if stop_speaking:
            break
        stream.write(data)
        data = wf.readframes(chunk_size)

    # Stop and close the stream
    stream.stop_stream()
    stream.close()
    p.terminate()

def timer_finished():
    play_wav('C:\\Users\\advic\\Downloads\\mixkit-facility-alarm-sound-999.wav')

def alarm_finished():
    play_wav('C:\\Users\\advic\\Downloads\\mixkit-facility-alarm-sound-999.wav')

def send_email(service, to, subject, body):
    # convert email to base64 and use google api to send the email
    message = MIMEText(body)
    message['to'] = to
    message['subject'] = subject
    encoded_message = {'raw': base64.urlsafe_b64encode(message.as_bytes()).decode()}
    try:
        sent_message = service.users().messages().send(userId="me", body=encoded_message).execute()
        print(f'Sent message to {to} Message Id: {sent_message["id"]}')
    except HttpError as error:
        print(f'An error occurred: {error}')

def set_active_device(spotifyObject, device_name):
    devices = spotifyObject.devices()
    device_id = None

    for device in devices['devices']:
        if device['name'] == device_name:
            device_id = device['id']
            break

    if device_id:
        spotifyObject.transfer_playback(device_id, force_play=True)
        print(f"Playback transferred to {device_name}.")
    else:
        print(f"Device named {device_name} not found.")

def extract_artist_name(command):
    """
    Extract_artist_name 
    Purpose: Use NLP technique to extract either artist_name, song_name, or playlist to shuffle

    Parameters:
    param1 (String): param1 is the command the user has given. 

    Returns:
    String: The song name and artist name will be string variables

    Examples:
        Command = "play Everlong by Foo Fighters"
        results: song_name = Everlong, artist_name = Foo Fighters

        Command = "Shuffle Red Hot Chili Peppers"
        results: artist_name = Red Hot Chili Peppers

        Command = "Shuffle my playlist vibe"
        results: artist_name = vibe
    """
    command = command.lower()
    tokens = word_tokenize(command)
    # Assuming the artist's name follows 'play' and 'by' keywords
    if 'play' in tokens and 'by' in tokens:
        play_index = tokens.index('play')
        by_index = tokens.index('by')
        if by_index > play_index:
            # Extracting the artist's name as words between 'by' and end of the command
            artist_name = ' '.join(tokens[by_index + 1:])
            song_name = ' '.join(tokens[play_index + 1:by_index])

            # Some artist's names are not correctly interpeted by speech-to-text
            # Currently just manually change name to correct spelling
            if artist_name == "suicideboys":
                artist_name = "$uicideboy$"
            elif artist_name == "zac bryant":
                artist_name = "Zach Bryan"
            return artist_name, song_name
    # Shuffle can be used to shuffle artist, playlist, and personal playlist
    # Assuming needed info will follow 'shuffle'   
    elif 'shuffle' in tokens:
        # Check to shuffle personal playlist
        if 'playlist' in tokens and 'my' in tokens:
            # Assume sentence structure 'shuffle my playlist {name}'
            shuffle_index = tokens.index('shuffle')
            artist_name_tokens = tokens[shuffle_index + 3]
            artist_name = artist_name_tokens
            if artist_name == "bartholomew":
                artist_name = "barthalamule"
            return artist_name
        
        # fall through to shuffle artist   
        shuffle_index = tokens.index('shuffle')
        # sentence structure = shuffle {artist_name}
        artist_name_tokens = tokens[shuffle_index + 1:]
        artist_name = ' '.join(artist_name_tokens)
        if artist_name == "suicideboys":
            artist_name = "$uicideboy$"
        elif artist_name == "zac bryant":
            artist_name = "Zach Bryan"
        elif artist_name == "bartholomay":
            artist_name = "barthalamule"
        elif artist_name == "bartholomew":
            artist_name = "barthalamule"
        return artist_name
    # used to play a specific song
    elif 'play' in tokens:
        play_index = tokens.index('play')
        song_name = ' '.join(tokens[play_index +1:])
        return song_name
    return None

def shuffle_play_artist(spoken_input, spotifyObject):
    """
    Purpose: 
    Shuffle the different songs by an artits by iterating through their albums and collecting their tracks then starting playback
    on the list of collected songs

    Parameters:
    param1 (String): param1 is the spoken input of the user. 
    param2 (Object): param2 is the spotify object which contains info to connect with spotify api

    Returns:
    Begins playing shuffled songs by an artist in spotify

    Examples:
        Command = "Shuffle Foo Fighters"
        results: starts playing song by foo fighters
    """
    # extract the artist name from the users voive input
    artist_name = extract_artist_name(spoken_input)
    if artist_name:
        # Search for the artist
        results = spotifyObject.search(q='artist:' + artist_name, type='artist', limit=1)
        artists = results['artists']['items']
        if artists:
            artist_id = artists[0]['id']
            # Get the artist's albums
            albums_results = spotifyObject.artist_albums(artist_id, album_type='album')
            albums = albums_results['items']
            if albums:
                # Collect tracks from these albums
                all_tracks = []
                for album in albums:
                    album_id = album['id']
                    tracks_results = spotifyObject.album_tracks(album_id)
                    tracks = tracks_results['items']
                    all_tracks.extend(tracks)
                
                if all_tracks:
                    # Shuffle the track list
                    random.shuffle(all_tracks)
                    # Extract the URIs of the tracks
                    track_uris = [track['uri'] for track in all_tracks]

                    # Start playback on the active device
                    try:
                        spotifyObject.start_playback(uris=track_uris[:10])  # Play the first 10 shuffled tracks
                        print(f'Random tracks from {artist_name} are now playing.')
                    except spotipy.exceptions.SpotifyException as e:
                        print(f"Playback error: {e}")
                else:
                    print(f"No tracks found for albums of {artist_name}.")
            else:
                print(f"No albums found for {artist_name}.")
        else:
            print(f"Artist {artist_name} not found.")
    else:
        print("Could not find an artist's name in the command.")

def shuffle_play_playlist(spoken_input, spotifyObject):
    """
    Purpose: 
    Shuffle any playlist on spotify

    Parameters:
    param1 (String): param1 is the spoken input of the user. 
    param2 (Object): param2 is the spotify object which contains info to connect with spotify api

    Returns:
    Begins playing shuffled songs from a playlist in spotify

    Examples:
        Command = "Shuffle vibe"
        results: shuffle songs from the playlist vibe
    """
    # Extract playlist name from spoken input
    playlist_name = extract_artist_name(spoken_input)

    if playlist_name:
        # Search for the playlist
        results = spotifyObject.search(q='playlist:' + playlist_name, type='playlist', limit=1)
        playlists = results['playlists']['items']

        if playlists:
            playlist_id = playlists[0]['id']
            # Get the playlist's tracks
            tracks_results = spotifyObject.playlist_tracks(playlist_id)
            tracks = tracks_results['items']
            all_tracks = [track['track']['uri'] for track in tracks if track['track']]

            if all_tracks:
                # Randomly shuffle queried tracks
                random.shuffle(all_tracks)
                track_uris = all_tracks

                try:
                    spotifyObject.start_playback(uris=track_uris[:20])  # Play the first 20 shuffled tracks
                    print(f'Random tracks from {playlist_name} playlist are now playing.')
                except spotipy.exceptions.SpotifyException as e:
                    print(f"Playback error: {e}")
            else:
                print(f"No tracks found in {playlist_name} playlist.")
        else:
            print(f"Playlist {playlist_name} not found.")
    else:
        print("Could not find a playlist name in the command.")

def shuffle_play_my_playlist(spoken_input, spotifyObject):
    # Extract playlist name from spoken input
    playlist_name = extract_artist_name(spoken_input)

    if playlist_name:
        # Get user's playlists
        playlists = spotifyObject.current_user_playlists()
        playlist_id = None

        # Search for the specific playlist by name
        for playlist in playlists['items']:
            if playlist['name'].lower() == playlist_name.lower() and playlist['owner']['id'] == spotifyObject.me()['id']:
                playlist_id = playlist['id']
                break

        if playlist_id:
            # Get the playlist's tracks
            tracks_results = spotifyObject.playlist_tracks(playlist_id)
            tracks = tracks_results['items']
            all_tracks = [track['track']['uri'] for track in tracks if track['track']]

            if all_tracks:
                random.shuffle(all_tracks)
                track_uris = all_tracks

                # Start playback on the active device
                try:
                    spotifyObject.start_playback(uris=track_uris[:20])  # Play the first 20 shuffled tracks
                    print(f'Random tracks from {playlist_name} playlist are now playing.')
                except spotipy.exceptions.SpotifyException as e:
                    print(f"Playback error: {e}")
            else:
                print(f"No tracks found in {playlist_name} playlist.")
        else:
            print(f"Playlist {playlist_name} not found.")
    else:
        print("Could not find a playlist name in the command.")

def play_specific_song_artist(spoken_input, spotifyObject):
    # Play a specific song by a specific artist.
    artist_name, song_name = extract_artist_name(spoken_input)
    if song_name and artist_name:
        # Search for the song by the artist
        query = f"track:{song_name} artist:{artist_name}"
        results = spotifyObject.search(q=query, type='track', limit=1)
        tracks = results['tracks']['items']

        if tracks:
            track_uri = tracks[0]['uri']  # Extract the URI of the first track
            try:
                spotifyObject.start_playback(uris=[track_uri])  # Play the track
                print(f'Now playing {song_name} by {artist_name}.')
            except spotipy.exceptions.SpotifyException as e:
                print(f"Playback error: {e}")
        else:
            print(f"No tracks found for {song_name} by {artist_name}.")
    else:
        print("Could not find the song name and artist's name in the command.")

def play_top_song_by_name(spoken_input, spotifyObject):
    # Search for a song by name and play the top result.
    song_name = extract_artist_name(spoken_input)

    results = spotifyObject.search(q=f"track:{song_name}", type='track', limit=1)
    tracks = results['tracks']['items']

    if tracks:
        track_uri = tracks[0]['uri']  # Extract the URI of the first track
        try:
            spotifyObject.start_playback(uris=[track_uri])  # Play the track
            print(f'Now playing {song_name}.')
        except spotipy.exceptions.SpotifyException as e:
            print(f"Playback error: {e}")
    else:
        print(f"No tracks found for {song_name}.")

def continuous_listen(recognizer, microphone):
    # Continouly listen to mic to allow for wake word 
    while True:
        with microphone as source:
            audio = recognizer.listen(source)
        try:
            yield recognizer.recognize_google(audio)
        except sr.UnknownValueError:
            pass  # Handle non-recognizable speech silently
        except sr.RequestError as e:
            print(f"API request error: {e}")

def parse_command(command):
    # Implement NLP techniques to tokenize words from given spoken input
    words = word_tokenize(command.lower())
    return words

def list_spotify_devices(spotifyObject, device_name=None):
    devices = spotifyObject.devices()
    device_list = devices['devices']

    if not device_list:
        print("No active Spotify devices found.")
        return None

    print("Available devices:")
    device_id = None
    for device in device_list:
        print(f"Device Name: {device['name']}, Device ID: {device['id']}")
        if device_name and device['name'].lower() == device_name.lower():
            device_id = device['id']

    return device_id if device_name else device_list

def start_playback_on_device(spotifyObject, device_id, track_uris):
    try:
        # Ensure the intended device is active
        spotifyObject.transfer_playback(device_id, force_play=False)

        # Start playback
        spotifyObject.start_playback(uris=track_uris)
        print("Playback started on the device.")
    except spotipy.SpotifyException as e:
        print(f"Spotify API Error: {e}")
    except Exception as e:
        print(f"An error occurred: {e}")

def create_event(reminder_body, date_str, time_str):
    service = google_api_init('calendar', 'v3')

    # Combine date and time strings and convert to RFC3339 timestamp
    # Convert date_str from "MM/DD/YYYY" to "YYYY-MM-DD"
    date_obj = datetime.strptime(date_str, "%m/%d/%Y")
    iso_date_str = date_obj.strftime("%Y-%m-%d")

    # Combine and convert to ISO 8601 format
    datetime_str = f"{iso_date_str}T{time_str}:00"
    datetime_obj = datetime.fromisoformat(datetime_str)
    start_time = datetime_obj.isoformat()
    end_time = (datetime_obj + timedelta(minutes=30)).isoformat()

    event = {
        'summary': reminder_body,
        'start': {
            'dateTime': start_time,
            'timeZone': 'UTC-6',
        },
        'end': {
            'dateTime': end_time,
            'timeZone': 'UTC-6',
        },
        'reminders': {
            'useDefault': False,
            'overrides': [
                {'method': 'email', 'minutes': 24 * 60},
                {'method': 'popup', 'minutes': 10},
            ],
        },
    }

    try:
        event = service.events().insert(calendarId='primary', body=event).execute()
        print(f"Event created: {event.get('htmlLink')}")
    except HttpError as error:
        print(f'An error occurred: {error}')

def extract_event_details(command):
    command = command.lower()
    tokens = word_tokenize(command)

    if 'reminder' in tokens:
        try:
            to_index = tokens.index('to')
            on_index = tokens.index('on')
            at_index = tokens.index("at")

            # Extracting the reminder body
            rem_body = ' '.join(tokens[to_index + 1:on_index])

            # Extracting the date
            date_tokens = tokens[on_index + 1:at_index]
            # Remove ordinal suffixes like 'th', 'rd', etc.
            date_tokens = [re.sub(r'(st|nd|rd|th)', '', token) for token in date_tokens]
            date_str = ' '.join(date_tokens)

            # Check if a year is present in the date
            year_match = re.search(r'\b\d{4}\b', date_str)
            current_year = datetime.now().year
            if year_match:
                date_obj = datetime.strptime(date_str, "%B %d %Y")
            else:
                date_obj = datetime.strptime(date_str, "%B %d")
                date_str += f" {current_year}"
                # Check if the date has already passed
                if date_obj < datetime.now():
                    date_str = date_str.replace(str(current_year), str(current_year + 1))
                    date_obj = datetime.strptime(date_str, "%B %d %Y")

            formatted_date_str = date_obj.strftime("%m/%d/%Y")

            # Extracting the time
            time_str = ' '.join(tokens[at_index + 1:])

            return rem_body, formatted_date_str, time_str
        except (ValueError, IndexError):
            print("Command parsing error.")
            return None, None, None
    else:
        return None, None, None

def get_canvas_grades(api_url, access_token):
    headers = {'Authorization': f'Bearer {access_token}'}
    
    # Fetch courses
    courses_response = requests.get(f'{api_url}/courses', headers=headers)
    if courses_response.ok:
        courses = courses_response.json()
    else:
        print("Failed to fetch courses")
        return {}

    grades = {}
    for course in courses:
        # Ensure course is a dictionary
        if not isinstance(course, dict) or 'id' not in course or 'name' not in course:
            continue

        course_id = course['id']
        grades_response = requests.get(f'{api_url}/courses/{course_id}/grades', headers=headers)
        if grades_response.ok:
            course_grades = grades_response.json()
            grades[course['name']] = course_grades
        else:
            print(f"Failed to fetch courses. Status Code: {courses_response.status_code}, Response: {courses_response.text}")

    return grades

def extract_measurement(command):
    command = command.lower()
    tokens = word_tokenize(command)
    # Normalize tokens to remove any instances of 'a' 
    tokens = [token for token in tokens if token != 'a']
    many_index = tokens.index("many")
    in_index = tokens.index("in")

    # Extract measurments and amounts based location of common words
    convert_to = ' '.join(tokens[many_index + 1:in_index - 1])
    convert_from = ' '.join(tokens[in_index + 2:])
    amount = tokens[in_index + 1]

    # Normalize units to singular form
    convert_to = normalize_unit(convert_to)
    convert_from = normalize_unit(convert_from)
    amount = normalize_fraction(amount)

    if amount == 'half':
        amount = 0.5

    return convert_from, convert_to, amount

def normalize_unit(unit):
    # Remove 's' at the end if it's likely a plural
    if unit.endswith('s') and unit not in ['gas']:
        return unit[:-1]
    return unit

def normalize_fraction(amount):
    try:
        # Check if amount is a fraction and convert it to a decimal
        return str(float(Fraction(amount)))
    except ValueError:
        # If not a fraction, return the original amount
        return amount

def conversion(convert_from, convert_to, amount):
    # Convert amount to numeric if it's a word or string number
    amount = normalize_fraction(amount)
    try:
        amount = w2n.word_to_num(amount)
    except ValueError:
        try:
            amount = float(amount)
        except ValueError:
            return "Invalid amount."

    # Dictionary mapping unit to (base_unit, conversion factor to base unit)
    conversion_to_base = {
        'teaspoon': ('milliliter', 4.92892),
        'tablespoon': ('milliliter', 14.7868),
        'oz': ('milliliter', 29.5735),
        'cup': ('milliliter', 240),
        'pint': ('milliliter', 473.176),
        'quart': ('milliliter', 946.353),
        'gallon': ('milliliter', 3785.41),
        'milliliter': ('milliliter', 1),
        'liter': ('milliliter', 1000),
        'ounce': ('gram', 28.3495),
        'pound': ('gram', 453.592),
        'gram': ('gram', 1),
        'kilogram': ('gram', 1000),
    }

    # Convert to base unit first
    base_from, factor_from = conversion_to_base.get(convert_from, (None, None))
    base_to, factor_to = conversion_to_base.get(convert_to, (None, None))

    if base_from is None or base_to is None or base_from != base_to:
        return "Conversion not supported."

    # Convert from 'convert_from' to base unit, then from base unit to 'convert_to'
    amount_in_base = amount * factor_from
    final_amount = amount_in_base / factor_to

    return "{:.2f}".format(final_amount)

def get_weather_data(latitude, longitude):
    # Initial API request
    base_url = f"https://api.weather.gov/points/{latitude},{longitude}"
    response = requests.get(base_url)
    
    if response.status_code == 200:
        data = response.json()
        return {
            "forecast": data["properties"]["forecast"],
            "forecast_hourly": data["properties"]["forecastHourly"],
            "forecast_grid_data": data["properties"]["forecastGridData"],
            "observation_stations": data["properties"]["observationStations"]
        }
    else:
        return None

def get_forecast(url):
    response = requests.get(url)
    if response.status_code == 200:
        return response.json()
    else:
        return None

def location():
    g = geocoder.ip('me')
    return g.lat, g.lng


def main():

    client_id = os.getenv('SPOTIFY_CLIENT_ID')
    client_secret = os.getenv('SPOTIFY_CLIENT_SECRET')
    redirect_uri = 'http://localhost:8080/callback'
    scope = 'user-modify-playback-state user-read-playback-state' 

    recognizer = sr.Recognizer()
    mic = sr.Microphone()

    porcupine, pa, audio_stream = Initialize_porcupine()
    spotifyObject = auth_spotify(client_id, client_secret, redirect_uri, scope)

    gmail_service = google_api_init('gmail', 'v1')
    print("ready")

    try:
        while True:
            pcm = audio_stream.read(porcupine.frame_length)
            pcm = struct.unpack_from("h" * porcupine.frame_length, pcm)
            result = porcupine.process(pcm)
            if result >= 0:  # Wake word detected
                print("listening")
                with mic as source:
                    audio = recognizer.listen(source)
                try:
                    spoken_text = recognizer.recognize_google(audio)
                    if "stop listening" in spoken_text.lower():
                        print("Stopping listening...")
                    elif "shuffle" in spoken_text.lower() and "my" in spoken_text.lower() and "playlist" in spoken_text.lower():
                        shuffle_play_my_playlist(spoken_text, spotifyObject)
                    elif "shuffle" in spoken_text.lower() and "playlist" in spoken_text.lower():
                        shuffle_play_playlist(spoken_text, spotifyObject)
                    elif "shuffle" in spoken_text.lower():
                        shuffle_play_artist(spoken_text, spotifyObject)
                    elif "play" in spoken_text.lower() and "by" in spoken_text.lower():
                        play_specific_song_artist(spoken_text, spotifyObject)
                    elif "open garage door" in spoken_text.lower():
                        email = os.getenv('EMAIL')
                        send_email(gmail_service, email, "Open Door", "This is the body of the email")
                        threaded_speak("Sending command to open garage door.")
                    elif "close garage door" in spoken_text.lower():
                        email = os.getenv('EMAIL')
                        send_email(gmail_service, email, "Close Door", "This is the body of the email")
                        threaded_speak("Sending command to close garage door.")
                    elif "play" in spoken_text.lower():
                        play_top_song_by_name(spoken_text, spotifyObject)
                    elif "timer" in spoken_text.lower() or "alarm" in spoken_text.lower():
                        command_type, time_value, unit = extract_time_from_command(spoken_text)
                        if command_type == 'timer':
                            set_timer(time_value, unit)
                            threaded_speak(f"Timer has been set for {time_value} {unit}.")
                        elif command_type == 'alarm':
                            set_alarm(time_value)
                            threaded_speak(f"Alarm has been set for {time_value.strftime('%I:%M %p')}.")
                    elif "reminder" in spoken_text.lower():
                        reminder_body, date_str, time_str = extract_event_details(spoken_text)
                        create_event(reminder_body, date_str, time_str)
                    elif "you're incredible" in spoken_text.lower():
                        threaded_speak("I know you made me")
                    elif "what are my grades" in spoken_text.lower():
                        api_url = "https://iastate.instructure.com/api/v1"
                        access_token = os.getenv('CANVAS_ACCESS_TOKEN')
                        try:
                            grades = get_canvas_grades(api_url, access_token)
                            grades_summary = '\n'.join([f"{course}: {grade}" for course, grade in grades.items()])
                            threaded_speak(grades_summary)
                        except Exception as e:
                            print(f"Error fetching grades: {e}")
                            threaded_speak("Sorry, I couldn't fetch your grades.")
                    elif "how many" in spoken_text.lower() and "in" in spoken_text.lower():
                        convert_from, to, amount = extract_measurement(spoken_text)
                        final_amount = conversion(convert_from, to, amount)
                        threaded_speak(f"there are {final_amount} {to} in {amount} {convert_from}")
                    elif "forecast" in spoken_text.lower() and "week" in spoken_text.lower():
                        latitude, longitude = location()
                        weather_data = get_weather_data(latitude, longitude)
                        if weather_data:
                            forecast = get_forecast(weather_data["forecast"])
                        if forecast:
                            general_forecast = "General Forecast:" + forecast["properties"]["periods"][0]["detailedForecast"]
                            threaded_speak(general_forecast)
                        else:
                            threaded_speak("Failed to retrieve weather data.")
                    elif "weather" in spoken_text.lower() and "today" in spoken_text.lower():
                        latitude, longitude = location()
                        weather_data = get_weather_data(latitude, longitude)
                        if weather_data:
                            forecast_hourly = get_forecast(weather_data["forecast_hourly"])
                            if forecast_hourly:
                                hourly_forecasts = []
                                for period in forecast_hourly["properties"]["periods"][:12]:  # Limit to first 12 periods
                                    time = period['startTime'].split('T')[1].split('-')[0][:5]  # Extract and format the time
                                    temp = period['temperature']
                                    hourly_forecast = f"At {time}, it will be {temp} degrees."
                                    hourly_forecasts.append(hourly_forecast)

                                forecast_message = "Here's the forecast for the next 12 hours. " + " ".join(hourly_forecasts)
                                threaded_speak(forecast_message)
                                concatenated_forecasts = " ".join(hourly_forecasts)
                                print(concatenated_forecasts)                         
                        else:
                            threaded_speak("Failed to retrieve weather data.")
                    elif "stop" in spoken_text.lower():
                        stop_functions()
                except sr.UnknownValueError:
                    print("Sorry, I did not understand that.")
                except sr.RequestError as e:
                    print(f"Could not request results from Google Speech Recognition service; {e}")

    finally:
        porcupine.delete()
        audio_stream.close()
        pa.terminate()

if __name__ == "__main__":
    main()