#!/usr/bin/env python3
"""
Computer B - FIXED Synchronized Eye Gaze Sharing (Client)
Only shares gaze data DURING stages, not between stages
"""

import pylink
import os
import platform
import random
import time
import sys
import numpy as np
import socket
import threading
import json
import queue
from psychopy import visual, core, event, monitors, gui
from EyeLinkCoreGraphicsPsychoPy import EyeLinkCoreGraphicsPsychoPy
from string import ascii_letters, digits

# Network Configuration
LOCAL_IP = "100.1.1.11"  # Computer B's IP
REMOTE_IP = "100.1.1.10"  # Computer A's IP
GAZE_PORT = 8889
SEND_PORT = 8888
SYNC_PORT = 5555

# Global variables
el_tracker = None
win = None
remote_gaze_data = {'x': 0, 'y': 0, 'valid': False, 'timestamp': 0}
network_stats = {'sent': 0, 'received': 0, 'errors': 0}

# IMPORTANT: Gaze sharing control
GAZE_SHARING_ACTIVE = False  # Only share during stages

# Experiment variables
#
current_trial = 0
total_trials = 5
local_gaze_stats = {
    'total_attempts': 0,
    'samples_received': 0,
    'valid_gaze_data': 0,
    'missing_data': 0,
    'last_valid_gaze': (0, 0)
}

# Game sockets
game_send_socket = None
game_receive_socket = None

# Image and condition variables
images = {
    'face': [],
    'limb': [],
    'house': [],
    'car': []
}
conditions = {}

# Category mapping (consistent with Computer A)
CATEGORY_MAP = {
    0: 'face',
    1: 'limb',
    2: 'house',
    3: 'car'
}

# Switch to the script folder
script_path = os.path.dirname(sys.argv[0])
if len(script_path) != 0:
    os.chdir(script_path)

# Show only critical log message in the PsychoPy console
from psychopy import logging
logging.console.setLevel(logging.CRITICAL)

# Configuration variables
use_retina = False
dummy_mode = False
full_screen = True

print("=" * 60)
print("COMPUTER B - GAZE DATA SHARING WITH COMPUTER A + MEMORY GAME")
print("=" * 60)
print(f"Local IP: {LOCAL_IP}")
print(f"Remote IP: {REMOTE_IP}")

# Set up EDF data file name
edf_fname = 'COMP_B_GAZE'

# Prompt user to specify an EDF data filename
dlg_title = 'Computer B Gaze Sharing - Enter EDF File Name'
dlg_prompt = 'Please enter a file name with 8 or fewer characters\n[letters, numbers, and underscore].'

while True:
    dlg = gui.Dlg(dlg_title)
    dlg.addText(dlg_prompt)
    dlg.addField('File Name:', edf_fname)
    ok_data = dlg.show()
    if dlg.OK:
        print('EDF data filename: {}'.format(ok_data[0]))
    else:
        print('user cancelled')
        core.quit()
        sys.exit()

    tmp_str = dlg.data[0]
    edf_fname = tmp_str.rstrip().split('.')[0]

    allowed_char = ascii_letters + digits + '_'
    if not all([c in allowed_char for c in edf_fname]):
        print('ERROR: Invalid EDF filename')
    elif len(edf_fname) > 8:
        print('ERROR: EDF filename should not exceed 8 characters')
    else:
        break

# Set up folders
results_folder = 'results'
if not os.path.exists(results_folder):
    os.makedirs(results_folder)

time_str = time.strftime("_%Y_%m_%d_%H_%M", time.localtime())
session_identifier = edf_fname + time_str
session_folder = os.path.join(results_folder, session_identifier)
if not os.path.exists(session_folder):
    os.makedirs(session_folder)

def setup_network():
    """Setup UDP sockets for sending and receiving gaze data"""
    global send_socket, receive_socket
   
    try:
        # Socket for sending data to Computer A
        send_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        send_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        print(f"✓ Send socket created for {REMOTE_IP}:{SEND_PORT}")
       
        # Socket for receiving data from Computer A
        receive_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        receive_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        receive_socket.bind((LOCAL_IP, GAZE_PORT))
        receive_socket.settimeout(0.001)  # Non-blocking with short timeout
        print(f"✓ Receive socket bound to {LOCAL_IP}:{GAZE_PORT}")
       
        return True
    except Exception as e:
        print(f"✗ Network setup failed: {e}")
        return False
# Start network setup
if not setup_network():
    print("Failed to setup network. Exiting...")
    sys.exit()


# Connect to EyeLink
print("\n1. CONNECTING TO EYELINK")
print("-" * 30)
if dummy_mode:
    el_tracker = pylink.EyeLink(None)
    print("Running in DUMMY mode")
else:
    try:
        el_tracker = pylink.EyeLink("100.1.1.1")
        print("✓ Connected to EyeLink Host at 100.1.1.1")
       
        if el_tracker.isConnected():
            try:
                version = el_tracker.getTrackerVersionString()
                print(f"✓ Tracker version: {version}")
            except:
                print("⚠️  Could not get version string")
    except RuntimeError as error:
        print('ERROR:', error)
        print('Switching to dummy mode...')
        dummy_mode = True
        el_tracker = pylink.EyeLink(None)

# Open EDF file
edf_file = edf_fname + ".EDF"
try:
    el_tracker.openDataFile(edf_file)
    print(f"✓ Data file opened: {edf_file}")
except RuntimeError as err:
    print('ERROR:', err)
    if el_tracker.isConnected():
        el_tracker.close()
    core.quit()
    sys.exit()

# Configure tracker
print("\n2. CONFIGURING TRACKER")
print("-" * 25)
el_tracker.setOfflineMode()
pylink.msecDelay(100)

commands = [
    "clear_screen 0",
    "sample_rate 1000",
    "link_sample_data = LEFT,RIGHT,GAZE,HREF,RAW,AREA,HTARGET,GAZERES,BUTTON,STATUS,INPUT",
    "link_event_filter = LEFT,RIGHT,FIXATION,SACCADE,BLINK,MESSAGE,BUTTON,INPUT",
    "file_sample_data = LEFT,RIGHT,GAZE,HREF,RAW,AREA,HTARGET,GAZERES,BUTTON,STATUS,INPUT",
    "file_event_filter = LEFT,RIGHT,FIXATION,SACCADE,BLINK,MESSAGE,BUTTON,INPUT",
    "recording_parse_type = GAZE",
    "saccade_velocity_threshold = 30",
    "saccade_acceleration_threshold = 9500",
    "calibration_type = HV9"
]

for cmd in commands:
    el_tracker.sendCommand(cmd)
    pylink.msecDelay(10)

print("✓ Tracker configured for shared gaze recording")

# Set up display
print("\n3. SETTING UP DISPLAY")
print("-" * 25)
mon = monitors.Monitor('myMonitor', width=53.0, distance=70.0)
win = visual.Window(fullscr=full_screen, monitor=mon, winType='pyglet', units='pix', color=[0, 0, 0])

scn_width, scn_height = win.size
print(f"✓ Window: {scn_width} x {scn_height}")

if 'Darwin' in platform.system() and use_retina:
    scn_width = int(scn_width/2.0)
    scn_height = int(scn_height/2.0)

# Configure EyeLink graphics
el_coords = "screen_pixel_coords = 0 0 %d %d" % (scn_width - 1, scn_height - 1)
el_tracker.sendCommand(el_coords)
print(f"✓ Screen coordinates: {el_coords}")

genv = EyeLinkCoreGraphicsPsychoPy(el_tracker, win)
foreground_color = (-1, -1, -1)
background_color = win.color
genv.setCalibrationColors(foreground_color, background_color)

if os.path.exists('images/fixTarget.bmp'):
    genv.setTargetType('picture')
    genv.setPictureTarget(os.path.join('images', 'fixTarget.bmp'))

genv.setCalibrationSounds('', '', '')

if use_retina:
    genv.fixMacRetinaDisplay()

pylink.openGraphicsEx(genv)
print("✓ Graphics environment ready")


# Create visual elements
print("\n4. CREATING VISUAL ELEMENTS")
print("-" * 30)

# Local gaze marker (Computer B's own gaze) - Green theme
local_gaze_marker = visual.Circle(win=win, radius=20, fillColor='limegreen', lineColor='darkgreen', lineWidth=2)
local_gaze_sparkle1 = visual.Circle(win=win, radius=15, fillColor='lightgreen', lineColor='white', lineWidth=1)

# Remote gaze marker (Computer A's gaze) - Blue theme
remote_gaze_marker = visual.Circle(win=win, radius=20, fillColor='deepskyblue', lineColor='navy', lineWidth=2)
remote_gaze_sparkle1 = visual.Circle(win=win, radius=15, fillColor='lightblue', lineColor='white', lineWidth=1)

# Status display (smaller to make room for game)
status_background = visual.Rect(win=win, width=scn_width*0.9, height=60,
                               fillColor='darkgreen', lineColor='lightgreen', lineWidth=2,
                               pos=[0, scn_height//2 - 40])
status_text = visual.TextStim(win, text='', pos=[0, scn_height//2 - 40], color='lightgreen',
                             height=12, bold=True)





def draw_ui_elements():
    """Draw status bar, legend, and corners"""
    # Draw corners
    for corner in corners:
        corner.draw()
   
    # Draw status
    status_background.draw()
    remote_age = time.time() - remote_gaze_data.get('timestamp', 0)
    remote_status = "CONNECTED" if remote_age < 0.1 else f"DELAYED"
   
    status_text.setText(
        f"COMPUTER A - MEMORY GAME | Trial {current_trial}/{total_trials} | "
        f"Sent: {network_stats['sent']} Recv: {network_stats['received']}"
    )
    status_text.draw()
   
    # Draw legend
    legend_bg.draw()
    legend_text.draw()

# Add these missing UI elements after the existing visual elements creation
def create_missing_ui_elements():
    """Create missing UI elements that are referenced but not defined"""
    global game_instructions, question_mark, feedback_text, legend_bg, legend_text, corners
   
    # Game instructions text
    game_instructions = visual.TextStim(win, text='', pos=[0, -scn_height//2 + 100],
                                       color='white', height=18, bold=True, wrapWidth=scn_width*0.9)
   
    # Question mark for recall phase
    question_mark = visual.TextStim(win, text='?', pos=[0, 0], color='red',
                                   height=48, bold=True)
   
    # Feedback text
    feedback_text = visual.TextStim(win, text='', pos=[0, -scn_height//2 + 50],
                                   color='white', height=24, bold=True)
   
    # Legend background and text
    legend_bg = visual.Rect(win=win, width=300, height=120,
                           fillColor='darkblue', lineColor='lightblue', lineWidth=2,
                           pos=[scn_width//2 - 170, -scn_height//2 + 80])
   
    legend_text = visual.TextStim(win, text='GREEN: Your gaze\nBLUE: Partner gaze\nF=Face L=Limb\nH=House C=Car',
                                 pos=[scn_width//2 - 170, -scn_height//2 + 80],
                                 color='lightblue', height=12, bold=True)
   
    # Corner decorations
    corner_size = 30
    corners = []
    corner_positions = [
        [-scn_width//2 + corner_size//2, scn_height//2 - corner_size//2],  # Top-left
        [scn_width//2 - corner_size//2, scn_height//2 - corner_size//2],   # Top-right
        [-scn_width//2 + corner_size//2, -scn_height//2 + corner_size//2], # Bottom-left
        [scn_width//2 - corner_size//2, -scn_height//2 + corner_size//2]   # Bottom-right
    ]
   
    for pos in corner_positions:
        corner = visual.Rect(win=win, width=corner_size, height=corner_size,
                           fillColor='gold', lineColor='orange', lineWidth=2,
                           pos=pos)
        corners.append(corner)
     

def clear_screen(win):
    win.clearBuffer()
    win.flip()

def show_msg(win, text, wait_for_keypress=True):
    msg_background = visual.Rect(win, width=scn_width*0.7, height=scn_height*0.6,
                                fillColor='lightcyan', lineColor='darkgreen', lineWidth=5)
    msg = visual.TextStim(win, text, color='darkgreen', wrapWidth=scn_width*0.6,
                         height=22, bold=True)
   
    clear_screen(win)
   
    if wait_for_keypress:
        start_time = core.getTime()
        while True:
            current_time = core.getTime()
            pulse = 0.95 + 0.05 * np.sin((current_time - start_time) * 3)
            msg_background.setSize([scn_width*0.7*pulse, scn_height*0.6*pulse])
           
            win.clearBuffer()

            msg_background.draw()
            msg.draw()
            win.flip()
            core.wait(0.016)
           
            keys = event.getKeys()
            if keys:
                break
    else:
        msg_background.draw()
        msg.draw()
        win.flip()
   
    clear_screen(win)

def terminate_task():
    global el_tracker, send_socket, receive_socket
   
    print("\nCleaning up...")
   
    # Save game results
    if trial_results:
        results_file = os.path.join(session_folder, f"{session_identifier}_memory_results.txt")
        with open(results_file, 'w') as f:
            f.write("Trial\tPosition\tTarget\tResponse\tCorrect\tRT\n")
            for result in trial_results:
                f.write(f"{result['trial']}\t{result['target_position']}\t{result['target_category']}\t"
                       f"{result['response']}\t{result['correct']}\t{result['reaction_time']:.3f}\n")
       
        correct_count = sum(1 for r in trial_results if r['correct'])
        avg_rt = np.mean([r['reaction_time'] for r in trial_results])
        print(f"✓ Game results saved: {correct_count}/{len(trial_results)} correct, avg RT: {avg_rt:.2f}s")
   
    # Close network sockets
    try:
        send_socket.close()
        receive_socket.close()
        print("✓ Network sockets closed")
    except:
        pass
   
    if el_tracker and el_tracker.isConnected():
        try:
            if el_tracker.isRecording():
                el_tracker.stopRecording()
            el_tracker.setOfflineMode()
            el_tracker.sendCommand('clear_screen 0')
            pylink.msecDelay(500)
            el_tracker.closeDataFile()
           
            # Download EDF file
            local_edf = os.path.join(session_folder, session_identifier + '.EDF')
            try:
                el_tracker.receiveDataFile(edf_file, local_edf)
                print(f"✓ Data file saved: {local_edf}")
            except RuntimeError as error:
                print('Data file download error:', error)
           
            el_tracker.close()
        except Exception as e:
            print(f"Cleanup error: {e}")
   
    # Print final statistics
    if local_gaze_stats['total_attempts'] > 0:
        valid_rate = 100 * local_gaze_stats['valid_gaze_data'] / local_gaze_stats['total_attempts']
        print(f"\nFinal Statistics:")
        print(f"  Local gaze valid: {local_gaze_stats['valid_gaze_data']}/{local_gaze_stats['total_attempts']} ({valid_rate:.1f}%)")
        print(f"  Network sent: {network_stats['sent']}")
        print(f"  Network received: {network_stats['received']}")
        print(f"  Network errors: {network_stats['errors']}")
   
    win.close()
    core.quit()
    sys.exit()

# Show instructions
task_msg = 'Computer B - Gaze Data Sharing + Memory Game\n\n'
task_msg += 'This program will:\n'
task_msg += '• Track your eye gaze (green markers)\n'
task_msg += '• Send your gaze data to Computer A\n'
task_msg += '• Receive and display Computer A\'s gaze (blue markers)\n'
task_msg += '• Run a memory game with 5 trials\n\n'
task_msg += 'Memory Game Instructions:\n'
task_msg += '• Study a 6x6 grid of images for 10 seconds\n'
task_msg += '• Recall what was at a marked position\n'
task_msg += '• Press F=Face, L=Limbs, H=House, C=Car\n\n'
task_msg += 'Network Configuration:\n'
task_msg += f'• Local IP: {LOCAL_IP}\n'
task_msg += f'• Remote IP: {REMOTE_IP}\n'
task_msg += f'• Ports: {GAZE_PORT}/{SEND_PORT}\n\n'
task_msg += 'Controls:\n'
task_msg += '• SPACE = Recalibrate eye tracker\n'
task_msg += '• ESCAPE = Exit program\n\n'
if dummy_mode:
    task_msg += 'DUMMY MODE: Simulated eye tracking\n'
task_msg += 'Press ENTER to begin calibration'

show_msg(win, task_msg)

# Calibration
print("\n5. CALIBRATION")
print("-" * 15)
if not dummy_mode:
    try:
        print("Starting calibration...")
        el_tracker.doTrackerSetup()
        print("✓ Calibration completed")
       
        el_tracker.exitCalibration()
        el_tracker.setOfflineMode()
        pylink.msecDelay(500)
       
        win.winHandle.activate()
        win.flip()
        event.clearEvents()
       
    except RuntimeError as err:
        print('Calibration ERROR:', err)
        el_tracker.exitCalibration()
        win.winHandle.activate()
        win.flip()

show_msg(win, "Calibration complete!\n\nStarting gaze sharing and memory game session.\n\nPress any key to begin.")

# Add this right after calibration in both scripts:
print("Reactivating window...")
win.winHandle.activate()
win.flip()
event.clearEvents()
core.wait(1.0)  # Longer pause
print("Window reactivated, continuing...")

class RobustSyncClient:
    def __init__(self, client_ip='100.1.1.11', server_ip='100.1.1.10', port=5555):
        self.client_ip = client_ip
        self.server_ip = server_ip
        self.port = port
        self.socket = None
        self.running = False
        self.message_queue = queue.Queue()
       
    def start_client(self):
        """Start the synchronization client with robust settings"""
        self.socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.socket.setsockopt(socket.SOL_SOCKET, socket.SO_SNDBUF, 65536)
        self.socket.setsockopt(socket.SOL_SOCKET, socket.SO_RCVBUF, 65536)
       
#        # Platform-specific optimizations
#        try:
#            self.socket.setsockopt(socket.IPPROTO_UDP, socket.UDP_CORK, 0)
#        except (AttributeError, OSError):
#            pass
#        
#        try:
#            self.socket.setsockopt(socket.IPPROTO_IP, socket.IP_DONTFRAG, 1)
#        except (AttributeError, OSError):
#            pass
           
        try:
            self.socket.bind((self.client_ip, self.port))
            print(f"✓ Sync client bound to {self.client_ip}:{self.port}")
        except OSError as e:
            print(f"Bind failed, trying 0.0.0.0: {e}")
            self.socket.bind(('0.0.0.0', self.port))
            print(f"✓ Sync client bound to 0.0.0.0:{self.port}")
       
        self.socket.settimeout(0.1)  # FIXED: Longer timeout
        self.running = True
       
        # Start receiving thread
        self.receive_thread = threading.Thread(target=self._receive_messages, daemon=True)
        self.receive_thread.start()
       
    def send_message(self, message_type, data=None, retry_count=3):
        """Send message with retry mechanism"""
        if not self.socket:
            return False
           
        message = {
            'type': message_type,
            'timestamp': time.perf_counter(),
            'data': data or {}
        }
       
        for attempt in range(retry_count):
            try:
                message_json = json.dumps(message, separators=(',', ':'))
                message_bytes = message_json.encode('utf-8')
                self.socket.sendto(message_bytes, (self.server_ip, self.port))
                print(f"B: Sent {message_type} (attempt {attempt + 1})")
                return True
            except Exception as e:
                print(f"B: Send error (attempt {attempt + 1}): {e}")
                time.sleep(0.1)
        return False
               
    def _receive_messages(self):
        """Receive messages with better error handling"""
        while self.running:
            try:
                data, addr = self.socket.recvfrom(1024)
                receipt_time = time.perf_counter()
               
                message = json.loads(data.decode('utf-8'))
                message['sender_addr'] = addr
                message['receipt_time'] = receipt_time
               
                self.message_queue.put(message)
                print(f"B: Received {message.get('type', 'unknown')}")
               
                # Auto-respond to ping
                if message.get('type') == 'ping':
                    self.send_message('pong', {'client_ready': True})
               
            except socket.timeout:
                continue
            except Exception as e:
                if self.running:
                    print(f"B: Receive error: {e}")
                   
    def wait_for_message(self, expected_type, timeout=30):
        """Wait for specific message with longer timeout"""
        start_time = time.perf_counter()
        while time.perf_counter() - start_time < timeout:
            try:
                message = self.message_queue.get(timeout=0.01)
                if message.get('type') == expected_type:
                    return message
                else:
                    # Put it back if it's not what we want
                    self.message_queue.put(message)
            except queue.Empty:
                continue
        print(f"B: Timeout waiting for {expected_type}")
        return None
       
    def get_message(self, timeout=0.1):
        """Get any message with reasonable timeout"""
        try:
            return self.message_queue.get(timeout=timeout)
        except queue.Empty:
            return None
           
    def close(self):
        """Close the client"""
        self.running = False
        if self.receive_thread:
            self.receive_thread.join(timeout=1)
        if self.socket:
            self.socket.close()

def setup_gaze_network():
    """Setup gaze sharing network (separate from sync)"""
    global send_socket, receive_socket
   
    try:
        send_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        send_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
       
        receive_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        receive_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        receive_socket.bind((LOCAL_IP, GAZE_PORT))
        receive_socket.settimeout(0.001)
       
        # Start receiving thread
        receive_thread = threading.Thread(target=receive_gaze_data, daemon=True)
        receive_thread.start()
       
        print("✓ Gaze sharing network ready")
        return True
    except Exception as e:
        print(f"✗ Gaze network setup failed: {e}")
        return False

def send_gaze_data(gaze_x, gaze_y, valid=True):
    """Send gaze data only when sharing is active"""
    global network_stats, GAZE_SHARING_ACTIVE
   
    if not GAZE_SHARING_ACTIVE:
        return  # Don't send when not in a stage
   
    try:
        data = {
            'x': float(gaze_x),
            'y': float(gaze_y),
            'valid': valid,
            'timestamp': time.time(),
            'computer': 'B'
        }
       
        message = json.dumps(data).encode('utf-8')
        send_socket.sendto(message, (REMOTE_IP, SEND_PORT))
        network_stats['sent'] += 1
       
    except Exception as e:
        network_stats['errors'] += 1

def receive_gaze_data():
    """Continuously receive gaze data"""
    global remote_gaze_data, network_stats
   
    while True:
        try:
            data, addr = receive_socket.recvfrom(1024)
            gaze_info = json.loads(data.decode('utf-8'))
           
            if gaze_info.get('computer') == 'A':
                remote_gaze_data.update(gaze_info)
                network_stats['received'] += 1
               
        except socket.timeout:
            continue
        except Exception as e:
            network_stats['errors'] += 1
            time.sleep(0.001)

def update_local_gaze_display():
    """Update local gaze marker"""
    global local_gaze_stats
   
    if not GAZE_SHARING_ACTIVE:
        return  # Don't process when not sharing
   
    local_gaze_stats['total_attempts'] += 1
   
    try:
        sample = el_tracker.getNewestSample()
    except:
        sample = None
   
    if sample is not None:
        local_gaze_stats['samples_received'] += 1
       
        gaze_data = None
        if sample.isRightSample():
            try:
                gaze_data = sample.getRightEye().getGaze()
            except:
                pass
        elif sample.isLeftSample():
            try:
                gaze_data = sample.getLeftEye().getGaze()
            except:
                pass
       
        if gaze_data and gaze_data[0] != pylink.MISSING_DATA and gaze_data[1] != pylink.MISSING_DATA:
            local_gaze_stats['valid_gaze_data'] += 1
           
            # Convert coordinates and update display
            gaze_x = (gaze_data[0] - scn_width/2 )
            gaze_y = (scn_height/2 - gaze_data[1])

            print(gaze_x)
            print(gaze_y)
           
            if True: # abs(gaze_x) <= scn_width/2 and abs(gaze_y) <= scn_height/2:
                local_gaze_marker.setPos([gaze_x, gaze_y])
               
                # Animate sparkles
                sparkle_time = core.getTime()
                sparkle_offset1 = 15 * np.sin(sparkle_time * 3)
                sparkle_offset2 = 10 * np.cos(sparkle_time * 4)
                local_gaze_sparkle1.setPos([gaze_x + sparkle_offset1, gaze_y + sparkle_offset2])
               
                # Send gaze data
                send_gaze_data(gaze_data[0], gaze_data[1], True)
        else:
            local_gaze_stats['missing_data'] += 1
            send_gaze_data(0, 0, False)

def update_remote_gaze_display():
    """Update remote gaze marker"""
    global remote_gaze_data
   
    if not GAZE_SHARING_ACTIVE:
        return  # Don't display when not sharing
   
    if remote_gaze_data.get('valid', False):
        try:
            gaze_x = (remote_gaze_data['x'] - scn_width/2 )
            gaze_y = (scn_height/2 - remote_gaze_data['y'] )
           
            remote_gaze_marker.setPos([gaze_x, gaze_y])
           
            sparkle_time = core.getTime()
            sparkle_offset1 = 12 * np.cos(sparkle_time * 3.5)
            sparkle_offset2 = 8 * np.sin(sparkle_time * 4.5)
            remote_gaze_sparkle1.setPos([gaze_x + sparkle_offset1, gaze_y + sparkle_offset2])
           
        except Exception as e:
            pass

# Additional global variables for memory game
images = {
    'face': [],
    'limb': [],
    'house': [],
    'car': []
}
conditions = {}
grid_stimuli = []
grid_covers = []
grid_positions = []
target_cover = None
question_mark = None
target_category = None

# Category mapping (consistent between computers)
CATEGORY_MAP = {
    0: 'face',
    1: 'limb',
    2: 'house',
    3: 'car'
}

#!/usr/bin/env python3
"""
Computer B (Client) - Modified functions and run_synchronized_experiment
Add these functions and replace the existing run_synchronized_experiment
"""

# Add these new functions after the existing utility functions (identical to Computer A)
#!/usr/bin/env python3
"""
Computer B (Client) - Modified functions and run_synchronized_experiment
Add these functions and replace the existing run_synchronized_experiment
"""

# Add these new functions after the existing utility functions (identical to Computer A)

def load_conditions():
    """Load conditions from dyad_conditions.json"""
    global conditions
    try:
        with open('dyad_conditions.json', 'r') as f:
            data = json.load(f)
            conditions = {
                'hard': data['top_layouts_array_fixed_64']  # 64-element arrays for 8x8 grids
            }
        print("✓ Conditions loaded from dyad_conditions.json (hard difficulty - 8x8 grids)")
    except FileNotFoundError:
        print("dyad_conditions.json not found. Using default hard conditions.")
        # Default 64-element condition if file not found
        conditions = {
            'hard': [[2, 0, 1, 3, 2, 3, 0, 1, 3, 1, 2, 1, 0, 2, 0, 3,
                     1, 3, 2, 0, 3, 1, 0, 2, 0, 2, 3, 1, 2, 0, 1, 3,
                     3, 2, 0, 1, 1, 0, 3, 2, 2, 3, 1, 0, 1, 3, 2, 0,
                     0, 1, 3, 2, 3, 2, 1, 0, 1, 0, 2, 3, 3, 1, 0, 2]]
        }
    except Exception as e:
        print(f"Error loading conditions: {e}")
        conditions = {
            'hard': [[2, 0, 1, 3, 2, 3, 0, 1, 3, 1, 2, 1, 0, 2, 0, 3,
                     1, 3, 2, 0, 3, 1, 0, 2, 0, 2, 3, 1, 2, 0, 1, 3,
                     3, 2, 0, 1, 1, 0, 3, 2, 2, 3, 1, 0, 1, 3, 2, 0,
                     0, 1, 3, 2, 3, 2, 1, 0, 1, 0, 2, 3, 3, 1, 0, 2]]
        }

def load_all_images():
    """Load all images from stimuli folder"""
    global images
   
    stimuli_path = 'stimuli'
   
    # Category mapping with correct plurals
    category_folders = {
        'face': 'faces',
        'limb': 'limbs',
        'house': 'houses',
        'car': 'cars'
    }
   
    # Try to load images from each category
    for category_key, folder_name in category_folders.items():
        folder_path = os.path.join(stimuli_path, folder_name)
       
        if os.path.exists(folder_path):
            for i in range(10):  # Load 10 images per category (0-9)
                image_name = f"{folder_name}-{i}.png"
                image_path = os.path.join(folder_path, image_name)
               
                if os.path.exists(image_path):
                    try:
                        images[category_key].append(image_path)
                        if i == 0:  # Only print for first image of each category
                            print(f"✓ Found {folder_name} images")
                    except Exception as e:
                        print(f"Error loading {image_path}: {e}")
       
        # If no images loaded for this category, create placeholder paths
        if not images[category_key]:
            print(f"No images found for {category_key} in {folder_path}. Will use colored rectangles.")
            # Add placeholder entries
            for i in range(10):
                images[category_key].append(f"placeholder_{category_key}_{i}")
   
    print("✓ Image paths loaded")

def create_synchronized_grid(condition_array, seed):
    """Create 8x8 grid from 64-element condition array using shared seed"""
    global grid_stimuli, grid_covers, grid_positions, target_cover, cell_size
   
    # Clear previous grid data
    grid_stimuli = []
    grid_covers = []
    grid_positions = []
   
    # Grid setup - 8x8 logical grid with 1:1 physical mapping
    logical_grid_size = 8
   
    # Calculate grid spacing
    available_width = scn_width * 0.8
    available_height = scn_height * 0.7  # Leave space for UI elements
   
    grid_spacing_x = available_width / logical_grid_size
    grid_spacing_y = available_height / logical_grid_size
   
    # Use the smaller spacing to maintain square grid
    grid_spacing = min(grid_spacing_x, grid_spacing_y)
    cell_size = int(grid_spacing * 0.85)  # Cells are 85% of spacing
   
    # Calculate grid position (center of screen)
    start_x = -(logical_grid_size - 1) * grid_spacing / 2
    start_y = (logical_grid_size - 1) * grid_spacing / 2
   
    # Hard difficulty: condition is a 64-element array representing 8x8 pattern
    condition_categories = [CATEGORY_MAP[num] for num in condition_array]
   
    # ========== SYNCHRONIZED IMAGE SELECTION ==========
    # Get unique categories and sort them for consistent ordering across computers
    unique_categories = sorted(list(set(condition_categories)))
    
    # Generate deterministic image selections for each category
    selected_images = {}
    for i, category in enumerate(unique_categories):
        if len(images[category]) > 0:
            # Use seed + category-specific offset for deterministic selection
            image_seed = seed + hash(category) % 10000  # Hash category name for consistent offset
            random.seed(image_seed)
            selected_images[category] = random.randint(0, len(images[category]) - 1)
        else:
            selected_images[category] = 0
    
    # Reset to original seed for any remaining grid operations
    random.seed(seed)
    # ====================================================
   
    # Create 8x8 grid with 1:1 logical-to-physical mapping
    for row in range(8):
        for col in range(8):
            category = condition_categories[row * 8 + col]
            selected_image_idx = selected_images[category]
            
            # Calculate position for this single cell
            x_pos = start_x + col * grid_spacing
            y_pos = start_y - row * grid_spacing
           
            grid_positions.append((x_pos, y_pos))
           
            # Create stimulus
            if images[category][selected_image_idx].startswith('placeholder_'):
                # Use colored rectangle
                category_colors = {
                    'face': 'orange',
                    'limb': 'green',
                    'house': 'purple',
                    'car': 'yellow'
                }
                stimulus = visual.Rect(win=win, width=cell_size, height=cell_size,
                                     fillColor=category_colors[category],
                                     lineColor='white', lineWidth=2,
                                     pos=[x_pos, y_pos])
               
                text_stim = visual.TextStim(win, text=category[0].upper(), pos=[x_pos, y_pos],
                                          color='black', height=cell_size//4, bold=True)
               
                grid_stimuli.append({'rect': stimulus, 'text': text_stim, 'category': category, 'image_type': 'rect'})
            else:
                # Use actual image
                img_stim = visual.ImageStim(win, image=images[category][selected_image_idx],
                                          pos=[x_pos, y_pos], size=(cell_size, cell_size))
               
                grid_stimuli.append({'image': img_stim, 'category': category, 'image_type': 'image'})
           
            # Create cover
            cover = visual.Rect(win=win, width=cell_size, height=cell_size,
                              fillColor='gray', lineColor='white', lineWidth=2,
                              pos=[x_pos, y_pos])
            grid_covers.append(cover)
   
    # Create special target cover (bright red for recall phase)
    target_cover = visual.Rect(win=win, width=cell_size, height=cell_size,
                              fillColor='red', lineColor='white', lineWidth=3,
                              pos=[0, 0])  # Position will be set during recall phase
   
    print(f"✓ Synchronized 8x8 grid created with seed {seed}")

def draw_study_grid():
    """Draw the uncovered grid during study phase"""
    for stim in grid_stimuli:
        if stim['image_type'] == 'rect':
            stim['rect'].draw()
            stim['text'].draw()
        else:
            stim['image'].draw()

# 1. ADD NEW GLOBAL VARIABLE (add this near the top with other globals)
target_square_color = 'red'  # Controls the color of the target square

# 2. MODIFY draw_recall_grid() FUNCTION (replace the existing function)
def draw_recall_grid(target_pos, square_color='red'):
    """Draw covered grid with target marker in specified color"""
    # Draw all covers except target position
    for i, cover in enumerate(grid_covers):
        if i != target_pos:
            cover.draw()
   
    # Draw target cover with specified color and question mark
    target_pos_coords = grid_positions[target_pos]
    target_cover.setPos(target_pos_coords)
    target_cover.setFillColor(square_color)  # Use the specified color
    target_cover.draw()
   
    # Draw question mark at target position
    question_mark = visual.TextStim(win, text='?', pos=target_pos_coords,
                                   color='white', height=cell_size//2, bold=True)
    question_mark.draw()
 
def evaluate_response(response, correct_category):
    """Check if response is correct"""
    response_mapping = {
        'f': 'face',
        'l': 'limb',
        'h': 'house',
        'c': 'car'
    }
    return response_mapping.get(response.lower()) == correct_category

def run_synchronized_experiment():
    """Main experiment with stage synchronization - MODIFIED for grid memory task"""
    global current_trial, total_trials, GAZE_SHARING_ACTIVE
   
    # Load conditions and images
    load_conditions()
    load_all_images()
   
    # Setup networks
    if not setup_gaze_network():
        print("Failed to setup gaze network")
        return
   
    # Initialize sync client
    sync_client = RobustSyncClient(LOCAL_IP, REMOTE_IP, SYNC_PORT)
    sync_client.start_client()
   
    # Wait for server to start experiment
    print("B: Waiting for experiment to start...")
   
    start_msg = sync_client.wait_for_message('start_experiment', timeout=60)
    if not start_msg:
        print("B: Timeout waiting for experiment start")
        return
   
    # Acknowledge start
    sync_client.send_message('ack_start', {'client_ready': True})
   
    print("B: Starting synchronized experiment")
   
    # Start recording
    el_tracker.startRecording(1, 1, 1, 1)
   
    # Create visual elements for grid task
    stage_text = visual.TextStim(win, text="", height=24, pos=(0, -scn_height//2 + 50), color='white', bold=True)
    response_prompt = visual.TextStim(win, text="Press F=Face, L=Limb, H=House, C=Car", height=24, pos=(0, scn_height//2 - 100), color='yellow', bold=True)
    feedback_text = visual.TextStim(win, text="", height=48, pos=(0, 0), bold=True)
   
    data_log = []
    total_score = 0
   
    # Main experiment loop
    experiment_running = True
    while experiment_running:
        message = sync_client.get_message(timeout=0.1)
       
        if message:
            msg_type = message.get('type')
           
            if msg_type == 'stage_grid_display':
                # ========== STAGE 1: GRID DISPLAY ==========
                print("B: Stage 1 - Grid Display")
                GAZE_SHARING_ACTIVE = True
               
                # Extract trial parameters from server
                trial_data = message.get('data', {})
                current_trial = trial_data.get('trial_number', 0)
                trial_seed = trial_data.get('seed', 0)
                condition_array = trial_data.get('condition_array', [])
                target_position = trial_data.get('target_position', 0)
                correct_category = trial_data.get('target_category', '')
               
                # Create identical grid using server's parameters
                create_synchronized_grid(condition_array, trial_seed)
               
                # Acknowledge sync
                sync_client.send_message('stage_sync_ack', {'ready': True})
               
                # Display grid for 5 seconds WITH gaze sharing
                stage_clock = core.Clock()
                while stage_clock.getTime() < 7.0:
                    update_local_gaze_display()
                    update_remote_gaze_display()
                   
                    win.clearBuffer()
                   

                   
                    # Draw grid
                    draw_study_grid()
                    stage_text.setText(f"Trial {current_trial} - Study the grid ({7.0 - stage_clock.getTime():.1f}s)")
                    stage_text.draw()

                    # Draw gaze markers
                    if GAZE_SHARING_ACTIVE:
                        local_gaze_marker.draw()
                        local_gaze_sparkle1.draw()
                        if remote_gaze_data.get('valid', False):
                            remote_gaze_marker.draw()
                            remote_gaze_sparkle1.draw()
                           
                   
                    win.flip()
                    core.wait(0.016)

                   
                    keys = event.getKeys(['escape'])
                    if 'escape' in keys:
                        GAZE_SHARING_ACTIVE = False
                        sync_client.send_message('end_experiment')
                        terminate_task()
                        return
               
                GAZE_SHARING_ACTIVE = False
               
            elif msg_type == 'stage_response':
                # ========== STAGE 2: RESPONSE COLLECTION ==========
                print("B: Stage 2 - Response Collection")
                GAZE_SHARING_ACTIVE = False
               
                # Reset target square color for new trial
                event.clearEvents()  # Clear any leftover keypresses

                target_square_color = 'red'
               
                # Acknowledge sync
                sync_client.send_message('stage_sync_ack', {'ready': True})
               
                # Response collection WITH gaze sharing and color feedback
                client_response = None
                client_rt = None
                first_responder = None
                first_response = None
               
                response_clock = core.Clock()
                response_received = {'server': False, 'client': False}
               
                while not (response_received['server'] and response_received['client']):
#                    update_local_gaze_display()
#                    update_remote_gaze_display()
                   
                    win.clearBuffer()
                   
                    # Draw gaze markers
                    if GAZE_SHARING_ACTIVE:
                        local_gaze_marker.draw()
                        local_gaze_sparkle1.draw()
                        if remote_gaze_data.get('valid', False):
                            remote_gaze_marker.draw()
                            remote_gaze_sparkle1.draw()
                   
                    # Draw covered grid with target (color changes after first response)
                    draw_recall_grid(target_position, target_square_color)
                    response_prompt.draw()
                    stage_text.setText(f"Trial {current_trial} - What was at the red position?")
                    stage_text.draw()
                   
                    win.flip()
                   
                    # Check for client response
                    if not response_received['client']:
                        keys = event.getKeys(['f', 'l', 'h', 'c', 'escape'], timeStamped=response_clock)
                        if keys:
                            key, rt = keys[0]
                            if key == 'escape':
                                GAZE_SHARING_ACTIVE = False
                                sync_client.send_message('end_experiment')
                                terminate_task()
                                return
                            elif key in ['f', 'l', 'h', 'c']:
                                client_response = key.upper()
                                client_rt = rt
                                response_received['client'] = True
                               
                                # Check if this is the first response
                                if first_responder is None:
                                    first_responder = 'client'
                                    first_response = client_response
                                    target_square_color = 'green'  # Turn square green!
                                    print("B: First response detected - square turned green")
                               
                                sync_client.send_message('response_update', {
                                    'responder': 'client',
                                    'response': client_response,
                                    'rt': client_rt
                                })
                    else:
                        # Still check for escape even after responding
                        keys = event.getKeys(['f', 'l', 'h', 'c', 'escape'])
                        if keys:
                            for key_info in keys:
                                key = key_info[0] if isinstance(key_info, tuple) else key_info
                                if key == 'escape':
                                    GAZE_SHARING_ACTIVE = False
                                    sync_client.send_message('end_experiment')
                                    terminate_task()
                                    return
                                # Silently discard f, l, h, c keys

                   
                    # Check for server response
                    resp_msg = sync_client.wait_for_message('response_update', timeout=0.1)#get_message(timeout=0.1)
                    if resp_msg:
                        if resp_msg.get('type') == 'response_update':
                            resp_data = resp_msg.get('data', {})
                            if resp_data.get('responder') == 'server':
                                if not response_received['server']:
                                    response_received['server'] = True
                                   
                                    # Check if this is the first response
                                    if first_responder is None:
                                        first_responder = 'server'
                                        first_response = resp_data.get('response')
                                        target_square_color = 'green'  # Turn square green!
                                        print("B: First response (from server) detected - square turned green")
#                        else:
#                            sync_client.message_queue.put(resp_msg)
                       
               
                GAZE_SHARING_ACTIVE = False
               
            elif msg_type == 'stage_feedback':
                # ========== STAGE 3: FEEDBACK ==========
                print("B: Stage 3 - Feedback")
                GAZE_SHARING_ACTIVE = False
               
                # Extract feedback data
                feedback_data = message.get('data', {})
                trial_score = feedback_data.get('trial_score', 0)
                total_score = feedback_data.get('total_score', 0)
                first_responder = feedback_data.get('first_responder', '')
                first_response = feedback_data.get('first_response', '')
                correct_category = feedback_data.get('correct_category', '')
               
                # Acknowledge sync
                sync_client.send_message('stage_sync_ack', {'ready': True})
               
                # Display feedback for 1 second WITH gaze sharing (UNCHANGED)
                feedback_clock = core.Clock()
                while feedback_clock.getTime() < 1.0:
                    print(feedback_clock.getTime())
#                    update_local_gaze_display()
#                    update_remote_gaze_display()
                   
                    win.clearBuffer()
                   
                    # Draw gaze markers
                    if GAZE_SHARING_ACTIVE:
                        local_gaze_marker.draw()
                        local_gaze_sparkle1.draw()
                        if remote_gaze_data.get('valid', False):
                            remote_gaze_marker.draw()
                            remote_gaze_sparkle1.draw()
                   
                    # Draw feedback
                    feedback_text.setText(f"+{trial_score}")
                    feedback_text.setColor('green' if trial_score > 0 else 'red')
                    stage_text.setText(f"Answer: {correct_category} | First: {first_responder} ({first_response})")
                   
                    feedback_text.draw()
                    stage_text.draw()
                   
                    win.flip()
                    core.wait(0.016)
               
                GAZE_SHARING_ACTIVE = False
               
                win.clearBuffer()
                win.flip()
               
               
                spatial_info = {
                'cell_size': cell_size,
                'grid_positions': grid_positions,
                'grid_layout': [{'position_index': i, 'center_x': pos[0], 'center_y': pos[1],
                'category': grid_stimuli[i]['category']} for i, pos in enumerate(grid_positions)],
                'screen_dimensions': [scn_width, scn_height] }
                # Log data
                trial_log = {
                    'trial': current_trial,
                    'target_position': target_position,
                    'correct_category': correct_category,
                    'client_response': client_response if 'client_response' in locals() else None,
                    'client_rt': client_rt if 'client_rt' in locals() else None,
                    'first_responder': first_responder,
                    'first_response': first_response,
                    'trial_score': trial_score,
                    'total_score': total_score,
                    'spatial_layout': spatial_info,
                    'target_coordinates': grid_positions[target_position] if target_position < len(grid_positions) else None
                }
                data_log.append(trial_log)
               
                print(f"B: Trial {current_trial} completed. Score: {trial_score}")
               
            elif msg_type == 'end_experiment':
                print("B: Experiment ended by server")
                experiment_running = False
                break
       
#        # Show waiting screen when not in a stage
#        if not GAZE_SHARING_ACTIVE:
#            win.clearBuffer()
#            stage_text.setText(f"Waiting for next stage... Score: {total_score}")
#            stage_text.draw()
#            win.flip()
#            
#            keys = event.getKeys(['escape'])
#            if 'escape' in keys:
#                sync_client.send_message('end_experiment')
#                terminate_task()
#                break
   
    # Save data
    import pandas as pd
    df = pd.DataFrame(data_log)
    filename = f'sync_client_B_{time.strftime("%Y%m%d_%H%M%S")}.csv'
    df.to_csv(filename, index=False)
   
    final_score_pct = (total_score / total_trials) * 100 if total_trials > 0 else 0
    print(f"B: Experiment complete! Score: {total_score}/{total_trials} ({final_score_pct:.1f}%)")
   
    sync_client.close()
# Run the experiment
if __name__ == '__main__':
    run_synchronized_experiment()
