from psychopy import visual, core, event, gui, monitors
import random
import numpy as np
import os
import json
import csv
from datetime import datetime
import pylink
import sys
import platform
from string import ascii_letters, digits
from EyeLinkCoreGraphicsPsychoPy import EyeLinkCoreGraphicsPsychoPy

# Game settings
GRID_SIZE = 8
TOTAL_ROUNDS = 20
EASY_ROUNDS = 10
MEDIUM_ROUNDS = 10
DISPLAY_TIME = 5.0

# EyeLink settings
EYELINK_HOST = "100.1.1.1"
dummy_mode = False
use_retina = False

# Category mapping
CATEGORY_MAP = {
    0: 'face',
    1: 'limb',
    2: 'house',
    3: 'car'
}

# Image categories for key mapping
CATEGORIES = {
    'h': 'house',
    'c': 'car', 
    'f': 'face',
    'l': 'limb'
}

class MemoryGame:
    def __init__(self):
        # Initialize EyeLink first
        self.el_tracker = None
        self.genv = None
        self._setup_eyelink()
        
        # Create window
        self.win = visual.Window(
            size=[1024, 768],
            fullscr=False,
            color='black',
            units='pix'
        )
        
        # Get screen dimensions
        self.scn_width, self.scn_height = self.win.size
        
        # Setup EyeLink graphics after window creation
        self._setup_eyelink_graphics()
        
        # Create gaze marker for local eye tracking display
        self.gaze_marker = visual.Circle(
            win=self.win, 
            radius=15, 
            fillColor='limegreen', 
            lineColor='darkgreen', 
            lineWidth=2
        )
        self.gaze_sparkle = visual.Circle(
            win=self.win, 
            radius=10, 
            fillColor='lightgreen', 
            lineColor='white', 
            lineWidth=1
        )
        
        # Gaze tracking variables
        self.gaze_stats = {
            'total_attempts': 0,
            'valid_gaze_data': 0,
            'missing_data': 0
        }
        
        # Load conditions from JSON
        self.conditions = self._load_conditions()
        
        # Load all images from stimuli folder
        self.images = self._load_all_images()
        
        # Create gray covers
        self.gray_cover = visual.Rect(self.win, width=80, height=80, fillColor='gray')
        
        # Create question mark
        self.question_mark = visual.TextStim(
            self.win, 
            text='??', 
            color='white', 
            height=30,
            bold=True
        )
        
        # Instructions text
        self.instructions = visual.TextStim(
            self.win,
            text="Memory Game with Eye Tracking\n\nRemember the images in the grid.\nAfter 5 seconds, recall what's under the ?? marker.\n\nPress:\nH for House\nC for Car\nF for Face\nL for Limb\n\nGreen dot shows your gaze\n\nPress SPACE to start",
            color='white',
            height=30,
            wrapWidth=800
        )
        
        # Score tracking
        self.score = 0
        self.current_round = 0
        
        # Data collection
        self.trial_data = []
        
        # Calculate grid positions
        self.grid_positions = self._calculate_grid_positions()
        
        # Create trial list (randomized order of difficulties)
        self.trials = (['easy'] * EASY_ROUNDS + ['medium'] * MEDIUM_ROUNDS)
        random.shuffle(self.trials)
    
    def _setup_eyelink(self):
        """Initialize EyeLink connection"""
        print("Setting up EyeLink connection...")
        
        # Get EDF filename from user
        edf_fname = 'MEMORY'
        dlg = gui.Dlg("Enter EDF File Name")
        dlg.addField('File Name (8 chars max):', edf_fname)
        ok_data = dlg.show()
        
        if dlg.OK:
            edf_fname = ok_data[0][:8]  # Limit to 8 characters
        else:
            print('User cancelled')
            core.quit()
            sys.exit()
        
        # Connect to EyeLink
        if dummy_mode:
            self.el_tracker = pylink.EyeLink(None)
            print("Running in DUMMY mode")
        else:
            try:
                self.el_tracker = pylink.EyeLink(EYELINK_HOST)
                print(f"✓ Connected to EyeLink Host at {EYELINK_HOST}")
            except RuntimeError as error:
                print('ERROR:', error)
                print('Switching to dummy mode...')
                global dummy_mode
                dummy_mode = True
                self.el_tracker = pylink.EyeLink(None)
        
        # Open EDF file
        edf_file = edf_fname + ".EDF"
        try:
            self.el_tracker.openDataFile(edf_file)
            print(f"✓ EDF file opened: {edf_file}")
        except RuntimeError as err:
            print('ERROR:', err)
            if self.el_tracker.isConnected():
                self.el_tracker.close()
            core.quit()
            sys.exit()
        
        # Configure tracker
        self.el_tracker.setOfflineMode()
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
            self.el_tracker.sendCommand(cmd)
            pylink.msecDelay(10)
        
        print("✓ EyeLink configured")
    
    def _setup_eyelink_graphics(self):
        """Setup EyeLink graphics environment"""
        # Configure screen coordinates
        if 'Darwin' in platform.system() and use_retina:
            scn_width = int(self.scn_width/2.0)
            scn_height = int(self.scn_height/2.0)
        else:
            scn_width = self.scn_width
            scn_height = self.scn_height
        
        el_coords = "screen_pixel_coords = 0 0 %d %d" % (scn_width - 1, scn_height - 1)
        self.el_tracker.sendCommand(el_coords)
        
        # Setup graphics environment
        self.genv = EyeLinkCoreGraphicsPsychoPy(self.el_tracker, self.win)
        foreground_color = (-1, -1, -1)
        background_color = self.win.color
        self.genv.setCalibrationColors(foreground_color, background_color)
        
        # Setup calibration target
        if os.path.exists('images/fixTarget.bmp'):
            self.genv.setTargetType('picture')
            self.genv.setPictureTarget(os.path.join('images', 'fixTarget.bmp'))
        
        self.genv.setCalibrationSounds('', '', '')
        
        if use_retina:
            self.genv.fixMacRetinaDisplay()
        
        pylink.openGraphicsEx(self.genv)
        print("✓ EyeLink graphics ready")
    
    def _calibrate_eyelink(self):
        """Run EyeLink calibration"""
        if not dummy_mode:
            try:
                print("Starting calibration...")
                self.el_tracker.doTrackerSetup()
                print("✓ Calibration completed")
                
                self.el_tracker.exitCalibration()
                self.el_tracker.setOfflineMode()
                pylink.msecDelay(500)
                
                self.win.winHandle.activate()
                self.win.flip()
                event.clearEvents()
                
            except RuntimeError as err:
                print('Calibration ERROR:', err)
                self.el_tracker.exitCalibration()
                self.win.winHandle.activate()
                self.win.flip()
    
    def _update_gaze_display(self):
        """Update local gaze marker display"""
        self.gaze_stats['total_attempts'] += 1
        
        try:
            sample = self.el_tracker.getNewestSample()
        except:
            sample = None
        
        if sample is not None:
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
                self.gaze_stats['valid_gaze_data'] += 1
                
                # Convert coordinates for display
                gaze_x = gaze_data[0] - self.scn_width/2
                gaze_y = self.scn_height/2 - gaze_data[1]
                
                if abs(gaze_x) <= self.scn_width/2 and abs(gaze_y) <= self.scn_height/2:
                    self.gaze_marker.setPos([gaze_x, gaze_y])
                    
                    # Animate sparkle
                    sparkle_time = core.getTime()
                    sparkle_offset_x = 8 * np.sin(sparkle_time * 3)
                    sparkle_offset_y = 6 * np.cos(sparkle_time * 4)
                    self.gaze_sparkle.setPos([gaze_x + sparkle_offset_x, gaze_y + sparkle_offset_y])
            else:
                self.gaze_stats['missing_data'] += 1
    
    def _draw_gaze_markers(self):
        """Draw gaze markers on screen"""
        self.gaze_marker.draw()
        self.gaze_sparkle.draw()
    
    def _load_conditions(self):
        """Load conditions from conditions.json"""
        try:
            with open('conditions.json', 'r') as f:
                data = json.load(f)
                return data['top_layouts_array_fixed_4']
        except FileNotFoundError:
            print("conditions.json not found. Using default conditions.")
            # Default conditions if file not found
            return [
                [2, 0, 1, 3],
                [3, 2, 0, 1],
                [1, 3, 2, 0],
                [0, 1, 3, 2],
                [3, 1, 2, 0]
            ]
        except Exception as e:
            print(f"Error loading conditions: {e}")
            return [[2, 0, 1, 3]]  # Fallback
    
    def _load_all_images(self):
        """Load all images from stimuli folder - FIXED naming convention"""
        images = {
            'face': [],
            'limb': [],
            'house': [],
            'car': []
        }
        
        stimuli_path = 'stimuli'
        
        # Category mapping with correct plurals for folder names
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
                    # FIXED: Use plural folder name in image filename
                    image_name = f"{folder_name}-{i}.png"  # e.g., "cars-0.png"
                    image_path = os.path.join(folder_path, image_name)
                    
                    if os.path.exists(image_path):
                        try:
                            img = visual.ImageStim(self.win, image=image_path)
                            images[category_key].append(img)
                            if i == 0:  # Only print for first image of each category
                                print(f"✓ Found {folder_name} images")
                        except Exception as e:
                            print(f"Error loading {image_path}: {e}")
            
            # If no images loaded for this category, create colored rectangles
            if not images[category_key]:
                print(f"No images found for {category_key}. Using colored rectangles.")
                colors = {'face': 'yellow', 'limb': 'green', 'house': 'blue', 'car': 'red'}
                for i in range(10):
                    rect = visual.Rect(self.win, width=80, height=80, fillColor=colors[category_key])
                    images[category_key].append(rect)
        
        return images
    
    def _calculate_grid_positions(self):
        """Calculate pixel positions for 8x8 grid"""
        positions = []
        start_x = -280  # Start position for grid
        start_y = 280
        spacing = 80    # Space between grid items
        
        for row in range(GRID_SIZE):
            for col in range(GRID_SIZE):
                x = start_x + col * spacing
                y = start_y - row * spacing
                positions.append((x, y))
        
        return positions
    
    def _create_grid_from_condition(self, condition, difficulty):
        """Create grid from condition array"""
        # condition is a 4-element array representing 2x2 pattern
        # Convert numbers to categories
        condition_categories = [CATEGORY_MAP[num] for num in condition]
        
        # Create grid based on difficulty
        grid_images = []
        grid_image_indices = []  # Track which specific image was used
        
        if difficulty == 'easy':
            # Each position in 2x2 becomes a 4x4 block
            for small_row in range(2):
                for small_col in range(2):
                    category = condition_categories[small_row * 2 + small_col]
                    # Randomly select one image from this category
                    selected_image_idx = random.randint(0, len(self.images[category]) - 1)
                    
                    # Fill 4x4 block with this image
                    for block_row in range(4):
                        for block_col in range(4):
                            grid_images.append(self.images[category][selected_image_idx])
                            grid_image_indices.append((category, selected_image_idx))
        
        else:  # medium
            # Each position in 2x2 becomes a 2x2 block
            # But we need to fill 8x8, so we need 4x4 pattern
            # Repeat the 2x2 pattern to make 4x4
            expanded_condition = []
            for row in range(4):
                for col in range(4):
                    original_idx = (row // 2) * 2 + (col // 2)
                    expanded_condition.append(condition[original_idx])
            
            # Convert to categories
            expanded_categories = [CATEGORY_MAP[num] for num in expanded_condition]
            
            # Now each position becomes a 2x2 block
            for small_row in range(4):
                for small_col in range(4):
                    category = expanded_categories[small_row * 4 + small_col]
                    # Randomly select one image from this category
                    selected_image_idx = random.randint(0, len(self.images[category]) - 1)
                    
                    # Fill 2x2 block with this image
                    for block_row in range(2):
                        for block_col in range(2):
                            grid_images.append(self.images[category][selected_image_idx])
                            grid_image_indices.append((category, selected_image_idx))
        
        return grid_images, grid_image_indices
    
    def _display_grid(self, grid_images):
        """Display the image grid with gaze tracking"""
        for i, img in enumerate(grid_images):
            x, y = self.grid_positions[i]
            img.pos = (x, y)
            img.size = (70, 70)  # Slightly smaller than cover
            img.draw()
        
        # Update and draw gaze markers
        self._update_gaze_display()
        self._draw_gaze_markers()
    
    def _display_covers(self, target_index):
        """Display gray covers over all positions, with ?? over target"""
        for i in range(64):
            x, y = self.grid_positions[i]
            self.gray_cover.pos = (x, y)
            self.gray_cover.draw()
            
            # Draw question mark over target position
            if i == target_index:
                self.question_mark.pos = (x, y - 50)  # Position above the square
                self.question_mark.draw()
        
        # Update and draw gaze markers
        self._update_gaze_display()
        self._draw_gaze_markers()
    
    def _get_user_response(self):
        """Get user response with gaze tracking display"""
        response_timer = core.Clock()
        
        while True:
            # Update gaze display while waiting for response
            self.win.clearBuffer()
            
            # Redraw covers and question mark
            for i in range(64):
                x, y = self.grid_positions[i]
                self.gray_cover.pos = (x, y)
                self.gray_cover.draw()
            
            # Find and redraw question mark (stored from previous call)
            if hasattr(self, '_current_target_index'):
                x, y = self.grid_positions[self._current_target_index]
                self.question_mark.pos = (x, y - 50)
                self.question_mark.draw()
            
            # Add instruction text
            instruction_text = visual.TextStim(
                self.win,
                text="What was under the ?? marker?\nH=House, C=Car, F=Face, L=Limb",
                pos=(0, -350),
                color='white',
                height=20
            )
            instruction_text.draw()
            
            # Update and draw gaze markers
            self._update_gaze_display()
            self._draw_gaze_markers()
            
            self.win.flip()
            
            keys = event.getKeys(keyList=['h', 'c', 'f', 'l', 'escape'])
            if keys:
                if keys[0] == 'escape':
                    self._cleanup_eyelink()
                    core.quit()
                return keys[0], response_timer.getTime()
            core.wait(0.01)
    
    def run_trial(self, difficulty):
        """Run a single trial with eye tracking"""
        # Send trial start message to EyeLink
        self.el_tracker.sendMessage(f"TRIAL_START {self.current_round} {difficulty}")
        
        # Select random condition
        condition = random.choice(self.conditions)
        
        # Create grid from condition
        grid_images, grid_image_indices = self._create_grid_from_condition(condition, difficulty)
        
        # Choose random target position
        target_index = random.randint(0, 63)
        target_category, target_image_idx = grid_image_indices[target_index]
        self._current_target_index = target_index  # Store for gaze display
        
        # Find correct key for target category
        correct_key = None
        for key, category in CATEGORIES.items():
            if category == target_category:
                correct_key = key
                break
        
        # Send grid display message
        self.el_tracker.sendMessage(f"GRID_DISPLAY_START target_pos_{target_index} target_cat_{target_category}")
        
        # Display images for 5 seconds with gaze tracking
        display_timer = core.Clock()
        while display_timer.getTime() < DISPLAY_TIME:
            self.win.clearBuffer()
            self._display_grid(grid_images)
            self.win.flip()
            core.wait(0.016)  # ~60 FPS
        
        # Send grid display end message
        self.el_tracker.sendMessage("GRID_DISPLAY_END")
        
        # Display covers with question mark and get response
        self.win.clearBuffer()
        self._display_covers(target_index)
        
        # Add instruction text
        instruction_text = visual.TextStim(
            self.win,
            text="What was under the ?? marker?\nH=House, C=Car, F=Face, L=Limb",
            pos=(0, -350),
            color='white',
            height=20
        )
        instruction_text.draw()
        self.win.flip()
        
        # Send response phase message
        self.el_tracker.sendMessage("RESPONSE_START")
        
        # Get response and measure time
        user_response, response_time = self._get_user_response()
        
        # Send response message
        self.el_tracker.sendMessage(f"RESPONSE {user_response} RT_{response_time:.3f}")
        
        # Check if correct
        correct = user_response == correct_key
        if correct:
            self.score += 1
            feedback = "Correct! +1 point"
            feedback_color = 'green'
        else:
            feedback = f"Incorrect. Answer was {correct_key.upper()}"
            feedback_color = 'red'
        
        # Send trial result message
        self.el_tracker.sendMessage(f"TRIAL_RESULT {'CORRECT' if correct else 'INCORRECT'}")
        
        # Record trial data
        trial_record = {
            'trial': self.current_round,
            'difficulty': difficulty,
            'condition': condition,
            'target_category': target_category,
            'target_image_index': target_image_idx,
            'target_position': target_index,
            'correct_key': correct_key,
            'user_response': user_response,
            'response_time': response_time,
            'correct': correct,
            'timestamp': datetime.now().isoformat()
        }
        self.trial_data.append(trial_record)
        
        # Show feedback with gaze tracking
        feedback_timer = core.Clock()
        while feedback_timer.getTime() < 1.5:
            self.win.clearBuffer()
            
            feedback_text = visual.TextStim(
                self.win,
                text=feedback,
                color=feedback_color,
                height=30
            )
            feedback_text.draw()
            
            # Update and draw gaze markers
            self._update_gaze_display()
            self._draw_gaze_markers()
            
            self.win.flip()
            core.wait(0.016)
        
        # Send trial end message
        self.el_tracker.sendMessage(f"TRIAL_END {self.current_round}")
        
        return correct
    
    def _save_data(self):
        """Save trial data to CSV file"""
        if not self.trial_data:
            return
        
        # Create filename with timestamp
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"memory_game_data_{timestamp}.csv"
        
        # Define CSV columns
        fieldnames = [
            'trial', 'difficulty', 'condition', 'target_category', 
            'target_image_index', 'target_position', 'correct_key', 
            'user_response', 'response_time', 'correct', 'timestamp'
        ]
        
        try:
            with open(filename, 'w', newline='', encoding='utf-8') as csvfile:
                writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
                writer.writeheader()
                writer.writerows(self.trial_data)
            
            print(f"Data saved to {filename}")
            
        except Exception as e:
            print(f"Error saving data: {e}")
    
    def _cleanup_eyelink(self):
        """Clean up EyeLink connection and save data"""
        if self.el_tracker and self.el_tracker.isConnected():
            try:
                if self.el_tracker.isRecording():
                    self.el_tracker.stopRecording()
                self.el_tracker.setOfflineMode()
                self.el_tracker.sendCommand('clear_screen 0')
                pylink.msecDelay(500)
                self.el_tracker.closeDataFile()
                
                # Download EDF file
                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                local_edf = f"memory_game_{timestamp}.EDF"
                try:
                    self.el_tracker.receiveDataFile("MEMORY.EDF", local_edf)
                    print(f"✓ EDF data saved: {local_edf}")
                except RuntimeError as error:
                    print('EDF download error:', error)
                
                self.el_tracker.close()
                
            except Exception as e:
                print(f"EyeLink cleanup error: {e}")
        
        # Print gaze statistics
        if self.gaze_stats['total_attempts'] > 0:
            valid_rate = 100 * self.gaze_stats['valid_gaze_data'] / self.gaze_stats['total_attempts']
            print(f"\nGaze Statistics:")
            print(f"  Valid gaze: {self.gaze_stats['valid_gaze_data']}/{self.gaze_stats['total_attempts']} ({valid_rate:.1f}%)")
            print(f"  Missing data: {self.gaze_stats['missing_data']}")
    
    def show_instructions(self):
        """Show game instructions with gaze tracking"""
        instruction_timer = core.Clock()
        
        while True:
            self.win.clearBuffer()
            self.instructions.draw()
            
            # Update and draw gaze markers
            self._update_gaze_display()
            self._draw_gaze_markers()
            
            self.win.flip()
            
            # Wait for spacebar
            keys = event.getKeys(keyList=['space', 'escape'])
            if keys:
                if keys[0] == 'escape':
                    self._cleanup_eyelink()
                    core.quit()
                elif keys[0] == 'space':
                    break
            
            core.wait(0.016)
    
    def show_final_score(self):
        """Show final score with gaze tracking"""
        score_text = visual.TextStim(
            self.win,
            text=f"Game Complete!\n\nFinal Score: {self.score}/{TOTAL_ROUNDS}\nAccuracy: {(self.score/TOTAL_ROUNDS)*100:.1f}%\n\nData has been saved to CSV and EDF files.\n\nPress SPACE to exit",
            color='white',
            height=40,
            wrapWidth=600
        )
        
        while True:
            self.win.clearBuffer()
            score_text.draw()
            
            # Update and draw gaze markers
            self._update_gaze_display()
            self._draw_gaze_markers()
            
            self.win.flip()
            
            keys = event.getKeys(keyList=['space', 'escape'])
            if keys:
                break
            
            core.wait(0.016)
    
    def run_game(self):
        """Run the complete game with eye tracking"""
        try:
            # Run calibration
            self._calibrate_eyelink()
            
            # Start recording
            self.el_tracker.startRecording(1, 1, 1, 1)
            self.el_tracker.sendMessage("GAME_START")
            
            # Show instructions
            self.show_instructions()
            
            # Run all trials
            for round_num in range(TOTAL_ROUNDS):
                self.current_round = round_num + 1
                difficulty = self.trials[round_num]
                
                # Show round info with gaze tracking
                round_timer = core.Clock()
                round_text = visual.TextStim(
                    self.win,
                    text=f"Round {self.current_round}/{TOTAL_ROUNDS}\nDifficulty: {difficulty.upper()}\n\nPress SPACE when ready",
                    color='white',
                    height=30
                )
                
                while True:
                    self.win.clearBuffer()
                    round_text.draw()
                    
                    # Update and draw gaze markers
                    self._update_gaze_display()
                    self._draw_gaze_markers()
                    
                    self.win.flip()
                    
                    keys = event.getKeys(keyList=['space', 'escape'])
                    if keys:
                        if keys[0] == 'escape':
                            self._cleanup_eyelink()
                            core.quit()
                        elif keys[0] == 'space':
                            break
                    
                    core.wait(0.016)
                
                # Run trial
                self.run_trial(difficulty)
                
                # Brief pause between trials
                core.wait(0.5)
            
            # End recording
            self.el_tracker.sendMessage("GAME_END")
            self.el_tracker.stopRecording()
            
            # Save data
            self._save_data()
            
            # Show final score
            self.show_final_score()
            
        except Exception as e:
            print(f"Error during game: {e}")
            # Try to save data even if there's an error
            self._save_data()
            self._cleanup_eyelink()
        finally:
            self._cleanup_eyelink()
            self.win.close()
            core.quit()

# Run the game
if __name__ == "__main__":
    # Create and run game
    game = MemoryGame()
    game.run_game()
