import os
import time
import threading
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler
from flask import Flask, render_template, redirect, url_for, request
from flask_socketio import SocketIO
from music21 import *
import more_itertools
import itertools
import serial
import time
import pandas as pd
import pygame as pg
import pygame.midi
import logging
import warnings

warnings.filterwarnings('ignore')
logging.basicConfig()
logging.getLogger('pygame').setLevel(logging.ERROR)
logging.getLogger('pandas').setLevel(logging.ERROR)

app = Flask(__name__)
socketio = SocketIO(app)

# Directory to monitor
sheet_music_dir = os.path.join(os.getcwd(), 'static', 'sheet')

# Placeholder playtime function (replace with your actual implementation)
# Initialize serial connection (adjust port as per your setup)
arduino = serial.Serial(port='/dev/cu.usbmodem142201', baudrate=115200, timeout=1)

def get_notes(path):
    score = converter.parse(path)
    score_parts = len(score.parts)
    notes = [[], []]
    times = [[0.0], [0.0]]

    for part in range(score_parts):
        for element in score.parts[part].flat:
            if isinstance(element, note.Note):
                notes[part].append([element.nameWithOctave])
                times[part].append(element.quarterLength)
            elif isinstance(element, chord.Chord):
                chord_notes = []
                for chord_note in element:
                    chord_notes.append(chord_note.nameWithOctave)
                notes[part].append([chord_notes])
                times[part].append(element.quarterLength)
            elif isinstance(element, note.Rest):
                notes[part].append(['rest'])
                times[part].append(element.quarterLength)

    cum_times = [[0.0], [0.0]]
    no_rests = [[], []]
    no_rests_cum_times = [[], []]

    for time in range(score_parts):
        for x in range(len(times[time]) - 1):
            prev_time = sum(times[time][0:x + 1])
            curr_time = times[time][x + 1]
            cum_times[time].append(prev_time + curr_time)

        for note1 in range(len(notes[time])):
            if notes[time][note1] != ['rest']:
                no_rests[time].append([notes[time][note1], cum_times[time][note1]])
                no_rests_cum_times[time].append(cum_times[time][note1])

    shared_elements = list(set(no_rests_cum_times[0]).intersection(*no_rests_cum_times[1:]))
    plain_list = []
    for part in range(score_parts):
        for pair in no_rests[part]:
            if pair[1] in shared_elements:
                plain_list.append(pair)

    new_plain_list = []
    for x in range(len(plain_list)):
        for y in range(x, len(plain_list)):
            if x != y and plain_list[x][1] == plain_list[y][1]:
                note_sim_list = list(more_itertools.collapse([plain_list[x][0], plain_list[y][0]]))
                new_plain_list.append([list(set(note_sim_list)), plain_list[x][1]])

    all_notes = list(itertools.chain(*no_rests))
    for element in all_notes:
        if element[1] not in shared_elements:
            new_plain_list.append(element)

    new_plain_list_ordered = sorted(new_plain_list, key=lambda x: x[1])
    final_list = []
    for duo in new_plain_list_ordered:
        final_list.append(duo[0])

    return final_list


def move_servo(pos):
    # Send position data to Arduino
    arduino.write(f"SERVO1:{pos}".encode())
    time.sleep(0.05)  # Small delay for command execution
    # Read response from Arduino
    response = arduino.readline().decode().strip()
    print(response)

def rotate_servo_2():
    # Trigger servo 2 to make a full rotation
    arduino.write("SERVO2:ROTATE".encode())
    time.sleep(0.05)  # Small delay for command execution
    # Read response from Arduino
    response = arduino.readline().decode().strip()
    print(response)

def playtime(song, strikes):
    note_list = ['A0', 'A#0', 'B0']
    for octave in range(1, 8):
        for note in ['C', 'C#', 'D', 'D#', 'E', 'F', 'F#', 'G', 'G#', 'A', 'A#', 'B']:
            note_list.append(note + str(octave))
    note_list.append('C8')
    key_num_list = range(21, 109)

    key_dict = dict(zip(key_num_list, note_list))

    def input_main(device_id=None):
        pg.init()
        pygame.midi.init()

        if device_id is None:
            input_id = pygame.midi.get_default_input_id()
        else:
            input_id = device_id
        i = pygame.midi.Input(input_id)

        data = {
            'time': [0],
            'name': ['C2'],
            'status': [128]
        }
        pressed = pd.DataFrame(data)
        pressed_keys = []
        
        right_count = 0
        wrong_count = 0

        going = True
        while going:
            events = pg.event.get()
            for e in events:
                if e.type in [pg.QUIT]:
                    going = False
                if e.type in [pg.KEYDOWN]:
                    going = False
                if e.type in [pygame.midi.MIDIIN]:
                    name = key_dict[e.__dict__['data1']]
                    timestamp = e.__dict__['timestamp']
                    status = e.__dict__['status']

                    new_row = pd.DataFrame({
                        "name": [name],
                        "status": [status],
                        "time": [timestamp]
                    })

                    pressed = pd.concat([pressed, new_row], ignore_index=True)

                    filtered_df = pressed[pressed['status'] == 128]
                    filtered_df['rank'] = filtered_df['time'].rank(ascending=False, method='dense')

                    if len(filtered_df) >= 2:
                        second_highest_time = filtered_df['time'].nlargest(2).iloc[-1]

                        result_df = pressed[(pressed['time'] < filtered_df['time'].max()) & (pressed['time'] > second_highest_time)]
                        unique_names = result_df['name'].unique().tolist()

                        if len(unique_names) > 0 and pressed.iloc[-1]['status'] == 128:
                            print(unique_names)
                            pressed_keys.append(unique_names)
                            
                            # Ensure the elements are hashable by flattening the lists
                            flattened_pressed_keys = set(flatten_list(pressed_keys[-1]))
                            flattened_song_keys = set(flatten_list(song[len(pressed_keys)-1]))
                            
                            if flattened_pressed_keys != flattened_song_keys:
                                wrong_count += 1
                                
                                if wrong_count % strikes == 0:
                                    print('Strike!')
                                    move_servo(0)
                                    time.sleep(0.05)
                                    move_servo(180)
                                    time.sleep(0.05)
                            else:
                                right_count += 1
                                
                            if len(pressed_keys) == len(song):
                                if right_count == len(song):
                                    print('Congratulations! You played it correctly!')
                                    rotate_servo_2()
                                else:
                                    print('Better luck next time!')
                                    
                                going = False
                                break

            if i.poll():
                midi_events = i.read(10)
                midi_evs = pygame.midi.midis2events(midi_events, i.device_id)

                for m_e in midi_evs:
                    pygame.event.post(m_e)

        del i
        pygame.midi.quit()

    if __name__ == "__main__":
        input_main()

# Helper function to flatten a list
def flatten_list(nested_list):
    flat_list = []
    for sublist in nested_list:
        if isinstance(sublist, list):
            flat_list.extend(flatten_list(sublist))
        else:
            flat_list.append(sublist)
    return flat_list


# File system event handler
class NewFileHandler(FileSystemEventHandler):
    def on_created(self, event):
        if event.src_path.endswith('.mxl'):
            file_name = os.path.basename(event.src_path)
            socketio.emit('new_file', {'file_name': file_name})
            playtime(get_notes(event.src_path),3)

# Monitor the directory in a separate thread
def monitor_directory():
    event_handler = NewFileHandler()
    observer = Observer()
    observer.schedule(event_handler, path=sheet_music_dir, recursive=False)
    observer.start()
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        observer.stop()
    observer.join()

# Start directory monitoring in a background thread
monitor_thread = threading.Thread(target=monitor_directory)
monitor_thread.daemon = True
monitor_thread.start()

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/search', methods=['GET'])
def search():
    query = request.args.get('query')
    if not query:
        return redirect(url_for('index'))
    
    # Redirect to MuseScore search page with the query for public domain scores
    musescore_search_url = f'https://musescore.com/sheetmusic?recording_type=public-domain&text={query}'
    return redirect(musescore_search_url)

if __name__ == '__main__':
    socketio.run(app, debug=False)
