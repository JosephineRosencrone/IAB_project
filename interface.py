import tkinter as tk
import pyttsx3              # pip install pyttsx3
import serial
import threading
import time
import numpy as np

# VOICE
engine = pyttsx3.init()

def speak(text):
    def run():
        engine.say(text)
        engine.runAndWait()
    threading.Thread(target=run, daemon=True).start()

# ACTIONS
def need_water_food():
    speak("I need water or food")

def feel_pain():
    speak("I feel pain")

def need_help():
    speak("I need someone to help me")


# UI SETUP
root = tk.Tk()
root.title("EMG Controller")
root.geometry("600x400")
root.configure(bg="#add8e6")

label = tk.Label(
    root,
    text="What do you need today?",
    font=("Arial",16,"bold"),
    bg="#add8e6"
)
label.pack(pady=20)

# UI FOR THRESHOLD VALUES
info_label = tk.Label(
    root,
    text="Calibration: ---",
    font=("Arial", 10),
    bg="#add8e6"
)
info_label.pack(pady=5)

button_frame = tk.Frame(root, bg="#add8e6")
button_frame.pack()

boton1 = tk.Button(button_frame, text="Water/Food", width=15, height=2, command=need_water_food)
boton2 = tk.Button(button_frame, text="I feel pain", width=15, height=2, command=feel_pain)
boton3 = tk.Button(button_frame, text="Need help", width=15, height=2, command=need_help)

boton1.pack(side="left", padx=5)
boton2.pack(side="left", padx=5)
boton3.pack(side="left", padx=5)

botones = [boton1, boton2, boton3]
selected = 0

# VISUAL SELECTION
def update_selection():
    for i, b in enumerate(botones):
        if i == selected:
            b.config(bg="gray30", fg="black", bd=4)
        else:
            b.config(bg="gray60", fg="black", bd=2)

# CONTROL FUNCTIONS
def move_right():
    global selected
    if selected < len(botones) - 1:
        selected += 1
        root.after(0, update_selection)

def move_left():
    global selected
    if selected > 0:
        selected -= 1
        root.after(0, update_selection)

def click():
    btn = botones[selected]

    btn.config(bg="blue")

    btn.invoke()

    def restore():
        update_selection()

    root.after(200, restore)


# SERIAL + SIGNAL LOGIC

PORT = 'COM6'                       # based on Arduino serial port
BAUD = 115200

SMOOTH_FAST = 0.3
SMOOTH_SLOW = 0.001


def serial_loop():
    global selected

    state = "center"
    # Ensure that signal must be stable for HOLD_TIME before moving (reduce chatter)
    right_start_time = None
    left_start_time = None
    HOLD_TIME = 0.08            # 80 ms (tune between 50–150 ms)

    ser = serial.Serial(PORT, BAUD)
    time.sleep(1)

    # EMG STATE
    emg_active = False
    last_click_time = 0
    
    print("Calibrating... keep relaxed and eyes centered")
    
    # Collect 300 samples to compute baseline + noise level
    eog_samples = []
    emg_samples = []
    while len(emg_samples) < 300:
        line = ser.readline().decode().strip()
        try:
            parts = line.split(",")
            eog_val = float(parts[0].split(":")[1])
            emg_val = float(parts[1].split(":")[1])

            eog_samples.append(eog_val)
            emg_samples.append(emg_val)
        except:
            continue
    
    eog_baseline = np.median(eog_samples)
    eog_noise = np.median(np.abs(eog_samples - eog_baseline))
    emg_baseline = np.median(emg_samples)
    emg_noise = np.median(np.abs(emg_samples - emg_baseline))
    
    print("Clench your jaw NOW")
    time.sleep(1)

    clench_samples = []
    while len(clench_samples) < 150:
        line = ser.readline().decode().strip()
        try:
            emg_val = float(line.split(",")[1].split(":")[1])
            clench_samples.append(emg_val)
        except:
            continue

    emg_peak = np.percentile(clench_samples, 90)
    emg_range = emg_peak - emg_baseline
    emg_high = emg_baseline + 0.85 * emg_range
    emg_low  = emg_baseline + 0.1 * emg_range
    
    print("EMG PEAK:", emg_peak)
    print("EMG HIGH:", emg_high)
    print("EOG baseline:", eog_baseline)
    print("EMG baseline:", emg_baseline)
    print("EOG noise:", eog_noise)
    print("EMG noise:", emg_noise)

    # FILTER STATE
    filtered_fast = eog_baseline
    filtered_slow = eog_baseline

    buffer = []

    # COOLDOWN BETWEEN ACTIONS
    last_move = 0
    cooldown = 0.3   # seconds

    # ADAPTIVE SYSTEM
    center = 0
    noise_est = eog_noise

    alpha_center = 0.001
    alpha_noise = 0.01
    
    while True:
        try:
            # Parse values
            line = ser.readline().decode().strip()
            try:
                parts = line.split(",")
                eog_val = float(parts[0].split(":")[1])
                emg_val = float(parts[1].split(":")[1])
            except:
                continue

            
            # MEDIAN FILTER
            buffer.append(eog_val)
            if len(buffer) > 5:         # if noisy change to 7, if laggy change to 3
                buffer.pop(0)

            eog_val = sorted(buffer)[len(buffer)//2]

            # DUAL FILTER
            filtered_fast = (1 - SMOOTH_FAST) * filtered_fast + SMOOTH_FAST * eog_val
            filtered_slow = (1 - SMOOTH_SLOW) * filtered_slow + SMOOTH_SLOW * eog_val

            deviation = filtered_fast - filtered_slow

            # ADAPTIVE CENTER (removes drift)
            if abs(deviation) < 2 * noise_est:
                center = (1 - alpha_center) * center + alpha_center * deviation
            dev = deviation - center

            # Ignore blink/artifacts spikes
            if abs(dev) > 6 * noise_est:
                continue
            
            # Prevent cross-direction contamination
            if dev > 0:
                left_start_time = None
            elif dev < 0:
                right_start_time = None
            
            # ADAPTIVE NOISE
            noise_est = (1 - alpha_noise) * noise_est + alpha_noise * abs(dev)
            noise_est = min(noise_est, 40)   # cap the noise

            # DYNAMIC THRESHOLDS
            RIGHT_ENTER = 2.2 * noise_est
            RIGHT_EXIT  = 0.8 * noise_est         # for hysteresis
            LEFT_ENTER  = -2.15 * noise_est
            LEFT_EXIT   = -0.8 * noise_est        # for hysteresis
            CENTER_ZONE = 0.5 * noise_est
            
            print(dev)
            print(f"EMG VAL: {emg_val:.2f} | HIGH: {emg_high:.2f} | LOW: {emg_low:.2f} | ACTIVE: {emg_active}")
            
            # Compute time between clicks
            now = time.time()

            # Rising edge detection = CLICK
            if emg_val > emg_high and not emg_active:
                emg_active = True
                
                if now - last_click_time > 1.0:     # time between clicks > 1s
                    root.after(0, click)
                    last_click_time = now

            # Reset when relaxed
            if emg_val < emg_low:
                emg_active = False

            # Print info to interface
            root.after(0, update_info,
                eog_baseline, eog_noise,
                emg_baseline, emg_noise,
                RIGHT_ENTER, LEFT_ENTER, dev,
                emg_high, emg_val)

            # CENTER ZONE (region where user is assumed to look straight)
            if abs(dev) < CENTER_ZONE:
                right_start_time = None
                left_start_time = None
                continue

            # TRIGGER RIGHT
            if state == "right":
                if dev < RIGHT_EXIT:
                    state = "center"
            
            elif dev > RIGHT_ENTER:
                if right_start_time is None:
                    right_start_time = time.time()

                elif time.time() - right_start_time > HOLD_TIME:
                    if state != "right" and time.time() - last_move > cooldown:
                        root.after(0, move_right)
                        last_move = time.time()
                        state = "right"
            else:
                right_start_time = None

            # TRIGGER LEFT
            if state == "left":
                if dev > LEFT_EXIT:
                    state = "center"
            
            elif dev < LEFT_ENTER:
                if left_start_time is None:
                    left_start_time = time.time()

                elif time.time() - left_start_time > HOLD_TIME:
                    if state != "left" and time.time() - last_move > cooldown:
                        root.after(0, move_left)
                        last_move = time.time()
                        state = "left"
            else:
                left_start_time = None

        except Exception as e:
            print("Error:", e)


# ADD INFO TO INTERFACE
def update_info(eog_baseline, eog_noise, emg_baseline, emg_noise, r, l, dev, emg_high, emg_val):
    text = (
        f"EOG baseline: {eog_baseline:.1f} | Noise: {eog_noise:.1f}\n"
        f"EMG baseline: {emg_baseline:.1f} | Noise: {emg_noise:.1f}\n"
        f"R: {r:.1f}  L: {l:.1f} EOG: {dev:.2f} \n"
        f"EMG thres: {emg_high:.1f} | EMG: {emg_val:.1f}"
    )
    info_label.config(text=text)


# START SERIAL THREAD
threading.Thread(target=serial_loop, daemon=True).start()

update_selection()
root.mainloop()