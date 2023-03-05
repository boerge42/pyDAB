# **********************************************************************************************
# 
#       pydab.py
# ----------------------
# Uwe Berger, 2022, 2023
#
# Hardware:
#    https://ugreen.eu/product/ugreen-dab-board/
#
# inspired by: 
#    https://www.raspberry-pi-geek.de/ausgaben/rpg/2020/10/dab-platine-fuer-den-raspi/
#    https://github.com/bablokb/simple-dab-radio
#
# ------------------------------------------------------------------------------------
#
# DAB-control:
# ------------
# init:
#   sudo ./radio_cli -b D -o 1
#
# tune (examble for BRB (german) --> "Radio BOB!"):
#    sudo ./radio_cli -b D -c 22 -e 5597 -f 2 -p -o 1
#
# shutdown:
#   sudo ./radio_cli -k
#
# scan/generate station-list
#   The file (ensemblescan__.json) should be created with: 
#      sudo radio_cli -b D -u 
#      sudo radio_cli -k
#      ...rename/move ensemblescan__.json --> {script_path}/stations.json" ...;-)... 
#
#
# audio-control (depending on your audio hardware configuration!):
# ----------------------------------------------------------------
# start audio-loop from DAB-board (I2S):
#   arecord -D sysdefault:CARD=dabboard -c 2 -r 48000 -f S16_LE  | aplay -q
#   or
#   alsaloop -C hw:1 -r 48000 -f S16_LE -c 2 -P hw:2 -t 200000 -d
#
#
#
# ---------
# Have fun!
#
# **********************************************************************************************
import tkinter as tk
from tkinter import ttk
from PIL import Image, ImageTk
import json
import os, subprocess, signal, shlex, sys

# ...defines...
btn_dx = 55
btn_dy = 55
logo_dx = 235
logo_dy = 235

script_path = os.path.split(os.path.abspath(__file__))[0]

station_logo_path = "logos"
button_icon_path = "icons"

# ******************************************************************
def get_icon(f, dx, dy):
    icon = Image.open(f)
    icon = icon.resize((dx, dy), Image.ANTIALIAS)
    icon = ImageTk.PhotoImage(icon)
    return icon

# ******************************************************************************************************************
class App:

    _RADIO_CLI    = "/home/pi/work/DABBoard/radio_cli"
    _CMD_DAB_START = _RADIO_CLI + " -b D -o 1"
    _CMD_DAB_STOP = _RADIO_CLI + " -k"
    _CMD_TUNER    = _RADIO_CLI + " -c {0} -e {1} -f {2} -p"
    #_CMD_I2S_PLAY = "arecord -D sysdefault:CARD=audiosensepi -c 2 -r 48000 -f S16_LE -q | aplay -q"
    _CMD_I2S_PLAY = "alsaloop -C hw:1 -r 48000 -f S16_LE -c 2 -P hw:2 -d -t 200000"
    _CMD_AUDIO_STOP = "killall alsaloop"
    _CMD_MUTE = "amixer set PCM mute -q"
    _CMD_UNMUTE = "amixer set PCM unmute -q"
    _CMD_VOLUME_MINUS = "amixer set PCM 3%- -q"
    _CMD_VOLUME_PLUS = "amixer set PCM 3%+ -q"
    
    _FNAME_SETTINGS = os.path.expanduser('~/.pydab.json')
    
    _i2s = 1
    _i2s_pid  = None

    # ******************************************************************
    def __init__(self, master):
        self.app_frame = tk.Frame(master)
        self.app_frame.pack()
        self.mute = False
        self.state = False
        # Icons
        self.icon_mute = get_icon(f"{script_path}/{button_icon_path}/icon_mute.png", btn_dx, btn_dy)
        self.icon_unmute = get_icon(f"{script_path}/{button_icon_path}/icon_unmute.png", btn_dx, btn_dy)
        self.icon_volume_minus = get_icon(f"{script_path}/{button_icon_path}/icon_volume_minus.png", btn_dx, btn_dy)
        self.icon_volume_plus = get_icon(f"{script_path}/{button_icon_path}/icon_volume_plus.png", btn_dx, btn_dy)
        self.icon_search = get_icon(f"{script_path}/{button_icon_path}/icon_search.png", btn_dx, btn_dy)
        self.icon_exit = get_icon(f"{script_path}/{button_icon_path}/icon_quit.png", btn_dx, btn_dy)
        self.f_app = tk.Frame(self.app_frame, bd=2)
        self.f_app.pack(side=tk.TOP, fill=tk.BOTH)
        f0 = tk.Frame(self.f_app, bd=2)
        f0.pack(side=tk.TOP, fill=tk.X)
        # stations
        f1 = tk.LabelFrame(f0, bd=2, text="Stations:")
        f1.pack(side=tk.LEFT, fill=tk.X)
        f1_ = tk.Frame(f1)
        f1_.pack(side=tk.TOP)
        # ...station-listbox
        f_stationlist = tk.Frame(f1_)
        f_stationlist.pack(side=tk.TOP)
        self.stations_lb=tk.Listbox(f_stationlist, width=25, height=9, font=("Arial", 18))
        self.stations_lb.pack(side=tk.LEFT, fill=tk.X, padx=5, pady=5)
        self.stations_scrollbar = tk.Scrollbar(f_stationlist, width=32)
        self.stations_scrollbar.pack(side = tk.RIGHT, fill = tk.BOTH)
        self.stations_lb.config(yscrollcommand = self.stations_scrollbar.set)
        self.stations_scrollbar.config(command = self.stations_lb.yview)
        self.stations_lb.bind('<<ListboxSelect>>', self._station_select)
        # ...stationdetails
        self.station_detail = tk.Label(f1_, text="-")
        self.station_detail.pack(side=tk.BOTTOM)
        self._fill_station_list()
        # ...infos for the station who is playing...
        f2 = tk.LabelFrame(f0, bd=2, text="playing:")
        f2.pack(side=tk.LEFT, fill=tk.BOTH)
        f2_ = tk.Frame(f2)
        f2_.pack(side=tk.TOP)
        self.playing_station = tk.Label(f2_, text="", font=("Arial", 20, "bold"))
        self.playing_station.pack(side=tk.TOP)
        self.playing_now = tk.Label(f2_, text="", width=52)
        self.playing_now.pack(side=tk.TOP)
        self.stationlogo = tk.Label(f2_)
        self.stationlogo.pack(side=tk.TOP)
        # ...buttons
        self.f4 = tk.LabelFrame(self.f_app, bd=2, text="Actions:")
        self.f4.pack(side=tk.TOP, fill=tk.X)
        self.btn_mute= self._my_button(self.f4, tk.LEFT, self.icon_mute, lambda:self._player_mute_toggle())
        self.btn_vol_minus = self._my_button(self.f4, tk.LEFT, self.icon_volume_minus, lambda:self._player_volume(0))
        self.btn_vol_plus = self._my_button(self.f4, tk.LEFT, self.icon_volume_plus, lambda:self._player_volume(1))
        self.btn_mute.configure(state="disable")
        self.btn_vol_minus.configure(state="disable")
        self.btn_vol_plus.configure(state="disable")
        self.btn_exit = self._my_button(self.f4, tk.RIGHT, self.icon_exit, lambda:self._quit_all(master))
        # DAB-Radio-Board start
        self.dab_start()
        # start audio-loop
        self.audio_start()

    # ******************************************************************
    def _cmd_call(self, cmd):
        rc = subprocess.call(shlex.split(cmd))
        print(f"return-code ({cmd}): {rc}")
        # vielleicht doch einfach nur os.system()???


    # ******************************************************************
    def dab_start(self):
        # start DAB-Board
        self._cmd_call(self._CMD_DAB_START)
        # read current settings
        self._read_settings()
    
    # ******************************************************************
    def audio_start(self):
        self._cmd_call(self._CMD_I2S_PLAY)

    # ******************************************************************
    def audio_stop(self):
        # kill alsaloop
        self._cmd_call(self._CMD_AUDIO_STOP)


    # ******************************************************************
    def dab_stop(self):
        # save current settings
        self._save_settings()
        # stop DAB-Board
        self._cmd_call(self._CMD_DAB_STOP)
        # stop audio
        self.audio_stop()
        
    # ******************************************************************
    def _quit_all(self, master):
        self.dab_stop()
        master.destroy()

    # ******************************************************************
    def _resize_image(self, fname, dx, dy):
        #print(fname)
        try:
            img = Image.open(fname)
        except:
            img = Image.open(f"{script_path}/logos/default.png")
        img_dx = img.width
        img_dy = img.height
        if img_dx != dx:
            img_dy = round(img_dy * dx/img_dx)
            img_dx = dx
        if img_dy != dy:
            img_dx = round(img_dx * dy/img_dy)
            img_dy = dy
        img = img.resize((img_dx, img_dy), Image.ANTIALIAS)
        img = ImageTk.PhotoImage(img)
        return img

    # ******************************************************************
    def _player_volume(self, flag):
        if flag:
           self._cmd_call(self._CMD_VOLUME_PLUS) 
        else:
           self._cmd_call(self._CMD_VOLUME_MINUS) 
            
            
    # ******************************************************************
    def _player_mute_toggle(self):
        if self.mute:
            self.mute=False
            self.btn_mute.configure(image=self.icon_mute)
            self._cmd_call(self._CMD_UNMUTE)
        else:
            self.mute=True
            self.btn_mute.configure(image=self.icon_unmute)
            self._cmd_call(self._CMD_MUTE)
        
    # ******************************************************************
    def _my_button(self, w, side, icon, cmd):
        b = tk.Button(w, height=btn_dy, width=2*btn_dx, image=icon, command=cmd)
        b.pack(side=side)
        return b
        
    # ******************************************************************
    def _fill_station_list(self):
        self.stations = self._read_stations(f"{script_path}/stations.json")
        self.stations_lb.delete(0, 'end')
        for l in self.stations:
            self.stations_lb.insert('end', l['label'])        
        pass
        

    # ******************************************************************
    def _tune_dab(self):
        # question: does the saved station number still exist?
        try:
            # ...yes, could theoretically be something completely different!
            self.station_detail.config(text=f"srvid: {self.stations[self.selected_station]['srvid']}; "
                                           +f"tune_idx: {self.stations[self.selected_station]['tune_idx']}; "
                                           +f"compid: {self.stations[self.selected_station]['compid']}")
            self.playing_station.config(text=self.stations[self.selected_station]['label'].strip());
            self.img=self._resize_image(f"{script_path}/{station_logo_path}/{self.stations[self.selected_station]['srvid']}.png", logo_dx, logo_dy)
            self.stationlogo.config(image=self.img)
            self.state=True
            self.btn_mute.configure(state="normal")
            self.btn_vol_minus.configure(state="normal")
            self.btn_vol_plus.configure(state="normal")                
            # tune DAB-Board
            self._cmd_call(self._CMD_TUNER.format(str(self.stations[self.selected_station]['compid']),
                                                  str(self.stations[self.selected_station]['srvid']),
                                                  str(self.stations[self.selected_station]['tune_idx']))
                          )
            # select station in gui-listbox
            self.stations_lb.select_set(self.selected_station)
            self.stations_lb.see(self.selected_station)
        except:
            # ... no, then continue as if no settings were there!
            pass

    # ******************************************************************
    def _station_select(self, event):
        selection = self.stations_lb.curselection()
        if selection:
            self.selected_station = selection[0]
            # tune dab-board
            self._tune_dab()
           
    # **********************************************************************************************
    def _save_settings(self):
        settings = {
            'volume':  'today, after five beer, no idea! Is it even necessary?',
            'station': self.selected_station,
            'name': self.stations[self.selected_station]['label']  # only informational
            }
        #print("saving settings to: %s" % self._FNAME_SETTINGS)
        with open(self._FNAME_SETTINGS,"w") as f:
            json.dump(settings,f,indent=2)  
            
            
    # **********************************************************************************************
    def _read_settings(self):
        if os.path.exists(self._FNAME_SETTINGS):
            with open(self._FNAME_SETTINGS,"r") as f:
                settings = json.load(f)
            self.selected_station = settings['station']
            self._tune_dab()
        else:
            pass
                

    # **********************************************************************************************
    def _read_stations(self, fname):
        # read services from station-list. 
        stations = []
        with open(fname,"r") as f:
            dabinfo = json.load(f)
        # scan all ensembles
        for ensemble in dabinfo["ensembleList"]:
            #print(ensemble["EnsembleNo"])
            # parse ensemble if valid
            if ensemble["DigradStatus"]["valid"]:
                services = ensemble["DigitalServiceList"]["ServiceList"]
                tune_idx = ensemble["DigradStatus"]["tune_index"]
                for service in services:
                    station = {}
                    station["tune_idx"] = tune_idx
                    if not service["AudioOrDataFlag"]:
                        station["label"]  = service["Label"]
                        station["srvid"]  = service["ServId"]
                        station["compid"] = service["ComponentList"][0]["comp_ID"]
                        stations.append(station)
        return stations
   


# **********************************************************************
def signal_handler(_signo, _stack_frame):
    global app
    app.dab_stop()
    sys.exit(0)


# **********************************************************************
def main():
    
    global app
    
    # setup signal handlers
    signal.signal(signal.SIGTERM, signal_handler)
    signal.signal(signal.SIGINT, signal_handler)
    
    
     
    root = tk.Tk()
    root.title("pyDAB+")
    
    w, h = root.winfo_screenwidth(), root.winfo_screenheight()
    if h > 500:
        root.geometry("800x420")
    else:
        root.geometry("%dx%d+0+0" % (w, h))
    app = App(root)
    root.mainloop()

# **********************************************************************
# **********************************************************************
# **********************************************************************
if __name__ == '__main__':
    main()
