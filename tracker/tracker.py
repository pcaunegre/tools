#!/usr/bin/python3
# -*- coding: utf-8 -*-

# ------------------------------------------------------------------------------
# tracker.py
# script to follow a list of pilots 
#      and rises an alert when a pilot is not moving
# 
# 
# Author: Pascal Caunegre
# Date: 2024/07/29
# Licence: CC-BY-NC-SA
# ------------------------------------------------------------------------------


import sys
import os
from datetime import datetime
import time
import csv
import json
import re
from requests_html import HTMLSession
from math import *

from tkinter import *
from tkinter import ttk
from tkinter import filedialog
import tkinter as tk
import tkinter.font as tkFont


FFVL_URL="https://data.ffvl.fr/api/?mode=json&key=79ef8d9f57c10b394b8471deed5b25e7&ffvl_tracker_key=all&from_utc_timestamp="
# REFRESH_PERIOD = 60
REFRESH_PERIOD = 10

# ------------------------------------------------------------------------------
# load pilot list from input csv file
# ------------------------------------------------------------------------------
def loadPilotList():
    
    global PILOT_FILTER, params
    PILOT_FILTER = {}
    if params['Filtrage'] != 'Fichier':
        print("not using pilot list to filter")
        return()
        
    if PILOTS_FILE=='' or PILOTS_FILE=='select a file' or not os.path.isfile(PILOTS_FILE):
        print("pilot list undefined or missing")
        return()
    
    with open(PILOTS_FILE, newline='') as csvfile:
        reader = csv.DictReader(csvfile)
        for row in list(reader):
            PILOT_FILTER[row['Pseudo']]={ "Name": row['Prenom'], "Surname": row['Nom']}
        csvfile.close()
    
    print(PILOT_FILTER)



# ------------------------------------------------------------------------------
# get info from database
# ------------------------------------------------------------------------------
def fetchDatabase():
    
    now = int(time.time()-60); # take position from last minute 
    url =FFVL_URL+str(now)
#     print("URL=%s" % url)
    ret = session.get(url)
    htmlContent = ret.content.decode('utf-8')
    
    #----debug
    with open("debug", 'w') as deb_file:
        print(htmlContent, file=deb_file)
        deb_file.close()
    #----
        
    l = json.loads(htmlContent)
    return(l)


# ------------------------------------------------------------------------------
# parse data from database
# update status for each pilot
# ------------------------------------------------------------------------------
def parseData(infolist):
    
    global PilotsStatus, params
    alarm = 0
    for elem in infolist:
        el = infolist[elem]
        pseudo=el['pseudo']
        ###TBR
        
        if params['Filtrage'] == 'Fichier':
            # is this pilot in list ?
            if not (pseudo in PILOT_FILTER): continue
        
        elif params['Filtrage'] == 'Distance':
            # is this pilot close enough ?
            if isPilotTooFar(el): continue
            
        
        
        if pseudo not in PilotsStatus: 
            # print("%s not in my list" % pseudo)
            continue
        
        (pilot,al) = PilotsStatus[pseudo]
        alarm += al
        
        # evaluate status of this pilot
        pilot = checkPilot(pilot,el)
        
        PilotsStatus[pseudo] = pilot

        print(el['pseudo'])
        print(el['last_latitude'])
        print(el['last_longitude'])
        print(el['last_altitude'])
    
    # save infos ib backup file
    savePilotTable()
    
    # TO BE REVIEWED
    if alarm: 
        command="mpg123 --frames 50 "+execpath+"/sound.mp3"
        os.system(command)    
    
# ------------------------------------------------------------------------------
# check status of a pilot
# ps : info list of pilot
# cur: current position
# 
# TakeOff : take off or not
# Landed  : has landed (no more moving after take off)
# 
# ------------------------------------------------------------------------------
def checkPilot(ps,cur):
    
    tof = 0; lan = 0; alarm = 0
    # rough distance calculation (in meter) from gps dec coord and altitude
    dist =  sqrt(((ps['last_lat']-cur['last_latitude'])*100000)**2+ \
            ((ps['last_lon']-cur['last_longitude'])*100000)**2+ \
            (ps['last_alt']-cur['last_altitude'])**2)
    print("--------------")
    print("Distance= %d m" % int(dist))
    
    deltaTime=int(cur['last_position_utc_timestamp_unix'])-int(ps['last_postime'])
    print("DeltaT= %d s" % deltaTime)
            
    # if speed is sent by device, use speed
    if 'last_h_speed' in cur:
        
        last_h_speed = cur['last_h_speed']
        print("Speed= %d km/h" % int(last_h_speed))
        # detect takeoff: speed of 10km/h
        if ps['TakeOff']==0:
            if (last_h_speed > 10): tof = 1
        
        else:
            if (last_h_speed < 5):  lan = 1
    
    
    # otherwise use distance from last record
    else:
        
        last_h_speed = -1
        # detect takeoff: move of 10m
        if ps['TakeOff']==0:
            if (dist > 10): tof = 1
        
        else:
            if (dist < 1):  lan = 1
    
    if tof:
        ps.update({'TakeOff': 1})
        print("Pilot %s takeoff V" % cur['pseudo'])
     
    if lan:
        ps.update({'Landed': 1})
        print("Pilot %s landed" % cur['pseudo'])

    # pilot landed but not cleared
    if (ps['Landed'] and ps['Cleared']==0):
        print("ALARM ! Pilot %s" % cur['pseudo'])
        alarm = 1
        

    ps.update({  "last_lat": cur['last_latitude'],\
                 "last_lon": cur['last_longitude'],\
                 "last_alt": cur['last_altitude'],\
                 "last_h_speed": int(last_h_speed),\
                 "last_postime": cur['last_position_utc_timestamp_unix']})
    return((ps,alarm))       

# -----------------------------------------------
# check whether pilot is close to the playground
# -----------------------------------------------
def isPilotTooFar(elem):
   
    global params
    lon=widgets['strvar']['Longitude'].get()
    lat=widgets['strvar']['Latitude'].get()
    alt=widgets['strvar']['ALtitude'].get()
    if len(lon) and len(lat) and len(alt):
        dist= sqrt(\
            ((lon-elem['last_longitude'])*100)**2 +\
            ((lat-elem['last_latitude'] )*100)**2 +\
            ( alt-elem['last_altitude'])**2 ) 
        if dist > params['MaxDistance']:
            return(1)
        else:
            return(0)
    else:
        # center point not defined, so no filtering
        return(0)

    
# -----------------------------------------------
# load pilot table from backup file
# -----------------------------------------------
def loadPilotTable():   
    
    global PilotsStatus
    if os.path.isfile(PILOTS_STATUS):
        with open(PILOTS_STATUS, 'r') as in_file:
            PilotsStatus = json.load(in_file)
            in_file.close()
    else:
        PilotsStatus = {}
    
# -----------------------------------------------
# save pilot table in backup file
# -----------------------------------------------
def savePilotTable():   
    
    global PilotsStatus
    with open(PILOTS_STATUS, 'w') as out_file:
        json.dump(PilotsStatus, out_file, indent = 4, sort_keys=True)
        out_file.close()      
    
        
# -----------------------------------------------
# table update
# -----------------------------------------------
def updatePilotTable():   
    
    global PilotsStatus
    
    horl = datetime.now()
    dt_string = horl.strftime("%H:%M:%S")
    widgets['dateLabel'].configure(text=dt_string)

    now = int(time.time())
    for p in PilotsStatus:
        elem=PilotsStatus[p]
        deltat = now-int(elem['last_postime'])
        (status,color) = calcStatus(elem)
        widgets['pilotStat'][p].sv.set(status)             # change the content of this widget
        widgets['pilotStat'][p].entry.configure(bg=color)   # change the color of this widget
        widgets['pilotRTim'][p].sv.set(deltat)

    savePilotTable() 

        
# -----------------------------------------------
# Calculate status
# -----------------------------------------------
def calcStatus(elem):

    status = '-'
    color = defaultbg         # default color #d9d9d9
    if elem['TakeOff']:
        status='En vol'
        color='green'
    if (elem['TakeOff'] and elem['Landed'] and (not elem['Cleared'])):
        status='ALERT'
        color='red'
    if elem['Cleared']:
        status='Safe'
        color=defaultbg

    return((status,color))


# -----------------------------------------------
# clear pilot status
# -----------------------------------------------
def clearPilotStatus(p):   
    
    global PilotsStatus
    
    elem=PilotsStatus[p]
    if elem['Cleared']:
        elem['Cleared']=0
    else:
        elem['Cleared']=1
    PilotsStatus[p]=elem
    updatePilotTable()
        
        
# ----------------------------------------------------------
#
# proc readParameterConfig
#        load the config of parameters instruments
#
# ----------------------------------------------------------
def readParameterConfig():
    
    global paramconfigfile
    f=paramconfigfile
    
    with open(f) as f:
        config = json.load(f)
        
    # print("Pin=%d"% rfpin)
    return(config)

# ----------------------------------------------------------
# 
# proc loadParams
#   load the parameters file
# 
# ----------------------------------------------------------
def loadParams():

    global paramstatusfile, params
    f=paramstatusfile

    # read the file
    if os.path.isfile(f):
        with open(f) as f:
            params = json.load(f)
        f.close()    
    else:
        # Create structure
        params = {}
    
    return() 


# ----------------------------------------------------------
# 
# proc writeParams
#   store the parameters file
# 
# ----------------------------------------------------------
def writeParams(params):

    global paramstatusfile
    f=paramstatusfile

    # write the status file
    with open(f, 'w') as out_file:
        json.dump(params, out_file, indent = 4, sort_keys=True)
        out_file.close()

# -----------------------------------------------
# Utilities
# -----------------------------------------------   
def saveParam():   
    
    global params       # preload defaults
    for el in widgets['paramTab']:
        params[el]=widgets['paramTab'][el].get()  # extract value from object
    
    writeParams(params)
    widgets['saveButtonParam'].configure(bg=defaultbg)


# -----------------------------------------------
# Manage starting process
# -----------------------------------------------
def processStart():

    #1. load the pilot filter (if any)
    loadPilotList()
    
    #2. load the pilot status (if any) in case of restart after a crash
    loadPilotTable()
        
    #3. begin to grab info
    infolist = fetchDatabase()
    if infolist is None: 
        print("fetch is void")    
    else:
        # filter and parse data
        parseData(infolist)
    
    
    #2. create pilot table and open panel
    
    
    #3. start the recurrent updater
     

# -----------------------------------------------
# Recurrent process
# -----------------------------------------------
def generalUpdater():   
    

#     #1. get all data
#     infolist = fetchDatabase()
#     if infolist is None: 
#         print("fetch is void")    
#     else:
#         #2. filter and parse data
#         parseData(infolist)
#     print("------------------------------------------------------------")

    
#     #TBR--- emulate for debug only
#     loadPilotTable()
#     #TBR---

    updatePilotTable()

    root.after(REFRESH_PERIOD*1000,generalUpdater)
    
    
# ------------------------------------------------------------------------------
# ------------------------------------------------------------------------------
# GUI functions
# ------------------------------------------------------------------------------
# ------------------------------------------------------------------------------

# ------------------------------------------------------------------------------
#
# Cell definition
# Create a table cell at the position x, y 
# with a default text and a given width
#
# ------------------------------------------------------------------------------
class Cell(ttk.Entry):
    def __init__(self,master,x,y, w=15, defval="?",togvals={}, pid='', wtype="lab", bgc='', options={'bd': 1, 'relief': 'groove'}):
        super().__init__(master)
        self.master = master
        self.x = x
        self.y = y
        self.w = w
        self.pid = pid
        self.opts = options
        
        if wtype=="lab":
            # making a label in the cell
            self.sv = tk.StringVar()
            self.sv.set(defval)
            if len(bgc):
                self.opts.update({"bg": bgc})
            self.entry = tk.Label(self.master,width=w, text=defval,textvariable=self.sv, **options)
        
        elif wtype=="ent":
            # making an entry in the cell
            self.sv = tk.StringVar()
            self.sv.set(defval)
            self.entry = ttk.Entry(self.master, textvariable=self.sv, width=w, **options) # state=DISABLED

        elif wtype=="scale":
            # making a slider
            # Scale(root, orient='horizontal', from_=0, to=10, resolution=0.1, tickinterval=2, length=350, label='Volume')        
#             self.sv = tk.StringVar()
#             self.sv.set(defval)
            self.entry = Scale(self.master, orient='horizontal',  **options)  #  length=350
            self.entry.set(defval) 
            self.entry.bind("<ButtonRelease-1>", self.ValueChanged)                   
        
        elif wtype=="tog":
            # making a toggle button in the cell
            self.vallist = togvals.copy()
            self.vallist.append(togvals.pop(0))
            self.sv = tk.StringVar()
            self.sv.set(defval)
            self.entry = tk.Button(self.master, textvariable=self.sv, command=self.OnClick, width=17, text=defval, padx=0, pady=1.5)   #bg="red", fg="blue",

        elif wtype=="radio":
            # making radio buttons in the cell
            self.sv = tk.StringVar()
            self.sv.set(defval)
            self.entry = tk.Frame(self.master)
            for butt in togvals:
                b = Radiobutton(self.entry, variable=self.sv, text=butt, command=self.ValueChanged, value=butt, font=font_def)
                b.pack(side='left', expand=1)    
            self.entry.bind("<ButtonRelease-1>", self.ValueChanged)                   

        elif wtype=="clearb":
            # making a single push button in the cell
             self.entry = tk.Button(self.master, command=self.OnPush, width=w, text=defval , padx=1, pady=1, bd=1)   #bg="red", fg="blue",
        
        self.entry.grid(column=self.x, row=self.y, padx=1, pady=1)

    def OnPush(self):
        clearPilotStatus(self.pid)
        
    def ValueChanged(self,newval=''):
        widgets['saveButtonParam'].configure(bg='Yellow')        

    def OnClick(self):
        curval=self.sv.get()
        indx=self.vallist.index(curval)
        newval=self.vallist[indx+1]
        self.sv.set(newval)
        self.ValueChanged()
        

#         self.ValueChanged()
# 
#         print('text')
#         print(self.entry.get('text'))
#         if self.entry.get('text')=='Clear':
#             clearPilotStatus(self.pid)
#             self.entry.configure(text="Undo") 
#         elif self.entry.get('text')=='Undo':
#             self.entry.configure(text="Clear") 
    

# ------------------------------------------------------------------------------
# PILOT PANEL
# ------------------------------------------------------------------------------
# ------------------------------------------------------------------------------
# Create pilots panel
# ------------------------------------------------------------------------------
def createPilotsPanel(nb):   
    
    frame=ttk.Frame(nb)
    frame.pack()
    nb.add(frame, text="Status pilotes", padding='2mm')
    Label(frame, relief='groove', font=font_title, bd=1, bg='#d9d98c', text="STATUS PILOTES",width=1000).pack(side='top', padx=2, pady=2)
    
    dateLabel=Label(frame, font=font_def, bd=1, text=dt_string)
    dateLabel.pack(side='top')
    widgets['dateLabel']=dateLabel

    canv = Canvas(frame, width=600, height=300, scrollregion=(0, 0, 600, 1200))
    canv.pack(side='left',fill='both', expand=1)

    sb = Scrollbar(frame,orient='vertical', width=20, command=canv.yview)
    sb.pack(side='right',fill='y')

    canv.configure(yscrollcommand=sb.set)
    
    createPilotTable(canv)


# -----------------------------------------------
# Create pilots table
# -----------------------------------------------
def createPilotTable(parent):   
    
    global PilotsStatus
    
    # first create a scrollable container
    pilottabframe=tk.Frame(parent)
    parent.create_window((0,0), window=pilottabframe, anchor='nw')    

    # header creation
    colInd=0
    for (header,width) in [['Pseudo',30], ['Prenom',30], ['Nom',30], ['Status',20], ['Dernier log',15], ['Clear',15] ]:
        Cell(pilottabframe,x=colInd,y=0, w=width, defval=header, options=optionsH)   
        colInd+=1
    
    now = int(time.time())
    # table body
    rawnbr=0
    for p in PilotsStatus:
        rawnbr+=1
        elem=PilotsStatus[p]
        deltat = now-int(elem['last_postime'])
        (status,color) = calcStatus(elem)
        Cell(pilottabframe, x=0,y=rawnbr, w=30, defval=p,               options=optionsC, bgc=defaultbg) 
        Cell(pilottabframe, x=1,y=rawnbr, w=30, defval=elem['Name'],    options=optionsC, bgc=defaultbg ) 
        Cell(pilottabframe, x=2,y=rawnbr, w=30, defval=elem['Surname'], options=optionsC, bgc=defaultbg ) 
        c=Cell(pilottabframe, x=3,y=rawnbr, w=20, defval=status,        options=optionsC, bgc=color ) 
        d=Cell(pilottabframe, x=4,y=rawnbr, w=15, defval=deltat,        options=optionsC, bgc=defaultbg ) 
        Cell(pilottabframe, x=5,y=rawnbr, w=15, wtype="clearb",defval="Clear/Undo",pid=p, options=optionsC, bgc=defaultbg ) 
        widgets['pilotStat'][p]=c   # keep an handle to change the status later
        widgets['pilotRTim'][p]=d
        
# ------------------------------------------------------------------------------
# OPTIONS PANEL
# ------------------------------------------------------------------------------
# -----------------------------------------------
# Create content of parameters panel
# -----------------------------------------------
def createParametersPanel(nb):   
    
    global PILOTS_FILE
    frame=ttk.Frame(nb)
    frame.pack()
    nb.add(frame, text="Parametres", padding='2mm')
    
    # - start button section
    buttonframe=tk.Frame(frame, relief='raised', height=10)
    buttonframe.pack(side='top',fill='both', expand=0)
    sb=Button(buttonframe, bd=3, highlightcolor='yellow',text="START !",height=1,width=20, command=processStart)
    sb.pack(side='left')
    Label(frame, relief='groove', bd=0).pack(side='top')        # spacer
    
    # - file section
    Label(frame, relief='groove', font=font_subtitle, bd=1, bg='#d9d98c',anchor='w', text="Fichier pilotes ",width=1000).pack(side='top')
    Label(frame, font=font_def,relief='flat', bd=3,anchor='w',fg='blue', text="Ce fichier facultatif liste les pilotes a filtrer( fichier .csv contenant : Pseudo,Nom,Prenom). ",width=1000).pack(side='top')
    fileframe=tk.Frame(frame, relief='raised', height=20)
    fileframe.pack(side='top',fill='both', expand=0)
    Label(fileframe, relief='flat', bd=1, text="Fichier pilote",width=15).pack(side='left')
    sv = tk.StringVar()
    sv.set(PILOTS_FILE)
    widgets['filesel']=sv
    l=Label(fileframe, relief='sunken', bd=1, font=font_ital, textvariable=sv,width=80)
    l.pack(side='left')
    widgets['filelab']=l
    sf=Button(fileframe,relief='raised', bd=3,text="Open",height=1, command=selectfile)
    sf.pack(side='left')
    Label(frame, relief='groove', bd=0).pack(side='top')        # spacer

    # - landing spot section
    Label(frame, relief='groove', font=font_subtitle, bd=1, bg='#d9d98c',anchor='w', text="Atterrissage ",width=1000).pack(side='top')
    Label(frame, font=font_def,relief='flat', bd=3,anchor='w',fg='blue', text="Le spot d'atterrissage sert a filter les pilotes par distance",width=1000).pack(side='top')
    menuframe=tk.Frame(frame, relief='raised', height=60)
    menuframe.pack(side='top',fill='both', expand=0)
    Label(menuframe, relief='flat', bd=1, text="Spot",width=15).grid(column=1, row=1, padx=1, pady=1)
    spotlist = getSpotList()
    widgets['strvar']['ld']=tk.StringVar()
    widgets['strvar']['ld'].set(spotlist[0])
    landsel = OptionMenu(menuframe, widgets['strvar']['ld'], *spotlist, command=updSpotEntry)
    landsel.config(width=25)    
    landsel.grid(column=2, row=1, padx=1, pady=1)
    rwnbr = 1
    for item in ['Latitude', 'Longitude', 'Altitude']:
        rwnbr+=1
        widgets['strvar'][item] = tk.StringVar()
        Label(menuframe, relief='flat', bd=1, text=item,width=15).grid(column=1, row=rwnbr, padx=1, pady=1)
        ttk.Entry(menuframe, textvariable=widgets['strvar'][item], width=30).grid(column=2, row=rwnbr, padx=1, pady=1) 
    
    # - options section
    Label(frame, relief='groove', font=font_subtitle, bd=1, bg='#d9d98c',anchor='w', text="Options",width=1000).pack(side='top')
    b=Button(frame,bd=3,text="Sauvegarder",height=10, command=saveParam)
    b.pack(side='right')
    widgets['saveButtonParam']=b

    canv = Canvas(frame, width=600, height=300, scrollregion=(0, 0, 600, 1200))
    canv.pack(side='left',fill='both', expand=1)

    sb = Scrollbar(frame,orient='vertical', width=20, command=canv.yview)
    sb.pack(side='right',fill='y')

    canv.configure(yscrollcommand=sb.set)
    
    createParamsTable(canv)

# -----------------------------------------------
# utility for spot selection
# -----------------------------------------------
def updSpotEntry(W):
    
    spot = widgets['strvar']['ld'].get()
    elem = getCoord(spot)
    for item in ['Latitude', 'Longitude', 'Altitude']:
        widgets['strvar'][item].set(elem[item])


# -----------------------------------------------
# utility for file selection
# -----------------------------------------------
def selectfile():

    global PILOTS_FILE
    ret = filedialog.askopenfilename()
    if len(ret):
        PILOTS_FILE = ret
        widgets['filesel'].set(PILOTS_FILE)
        widgets['filelab'].configure(font=font_def)


# -----------------------------------------------
# utility for drop down list
# -----------------------------------------------
def getSpotList():
    
    config = readParameterConfig()
    outlist = []
    for elem in config['spots']:
        name=elem['name']
        outlist.append(name)
    return(outlist)

# -----------------------------------------------
# return coord (lat lon alt) of a spot
# -----------------------------------------------
def getCoord(spot):
    
    config = readParameterConfig()
    outlist = []
    for elem in config['spots']:
        if elem['name']==spot:
            return(elem)

# -----------------------------------------------
# Create parameters table
# -----------------------------------------------
def createParamsTable(parent):
    
    global params
    # get config and last stored values
    config = readParameterConfig()
    # no more needed params = loadParams()
    widgets['prevParams']=params    # store current parameters 
    
    # store this object for future destroy/refresh
    widgets['paramsparentframe']=parent
    
    # first create a container
    paramstabframe=tk.Frame(parent)
    parent.create_window((0,0), window=paramstabframe, anchor='nw')    

    # Table headers creation
    Cell(paramstabframe,x=0, y=0, w=15, options=optionsH, defval='Parametre')   
    Cell(paramstabframe,x=1, y=0, w=30, options=optionsH, defval='Valeur')   
    Cell(paramstabframe,x=2, y=0, w=100, options=optionsH, defval='Description')   

    options={'height': 2}

    # Table body creation
    rawnbr=1
    for elem in config['parameters']:
        name=elem['name']
        Cell(paramstabframe,x=0,y=rawnbr,defval=name, w=15, options={'height': 2} )            # Id column
        
        value=""
        if 'def' in elem:
            value=elem['def']
            descrip = elem['descr'] + " (def. " + str(value) + ")"
        else:
            descrip = elem['descr']
            
        if name in params:
            value=params[name]
                
        typ=elem['type']
        met=elem['method']
        options={}
        if met=='scale':
            options={'length': 270}
            options['from_']=elem['from']
            options['to']=elem['to']
            options['resolution']=elem['res']
            c=Cell(paramstabframe,x=1,y=rawnbr,defval=value, w=30, wtype='scale', options=options) # Status column
            widgets['paramTab'][name]=c.entry
       
        elif met=='radio':
            c=Cell(paramstabframe,x=1,y=rawnbr,defval=value, togvals=elem['list'], w=30, wtype='radio', options=options) # Status column
            widgets['paramTab'][name]=c.sv   # 
        
        elif met=='entry':
            c=Cell(paramstabframe,x=1,y=rawnbr,defval=value, w=30, wtype='ent', options=options) 
            widgets['paramTab'][name]=c.sv   # 

        elif met=='label':
            c=Cell(paramstabframe,x=1,y=rawnbr,defval=value, w=30, wtype='lab', options=options) 
            widgets['paramTab'][name]=c.sv   # 

        elif wtype=="tog":
            # making a toggle button in the cell
            self.vallist = togvals.copy()
            self.vallist.append(togvals.pop(0))
            self.sv = tk.StringVar()
            self.sv.set(defval)
            self.entry = tk.Button(self.master, textvariable=self.sv, command=self.OnClick, width=17, text=defval, padx=0, pady=1.5)   #bg="red", fg="blue",
        
        Cell(paramstabframe,x=2,y=rawnbr,defval=descrip, options={'font': font_def, 'anchor': 'w'}, w=100) # Descr column
        rawnbr+=1













def getgeom(W):
    
    print("Geom")
    print("The width of Tkinter window:", root.winfo_width())
    print("The height of Tkinter window:", root.winfo_height())     
    print("Screen")
    print("The width of Tkinter window:", root.winfo_screenwidth())
    print("The height of Tkinter window:", root.winfo_screenheight())     
    
# ------------------------------------------------------------------------------
# ------------------------------------------------------------------------------
# -----------------------------
#   MAIN PROGRAM
# -----------------------------
# ------------------------------------------------------------------------------
# ------------------------------------------------------------------------------
# def
execpath=os.path.dirname(sys.argv[0])
paramconfigfile = execpath+"/.config"
paramstatusfile = os.environ['HOME']+"/.tracker.options"
PILOTS_STATUS   = os.environ['HOME']+"/.tracker.pilots"
PILOTS_FILE     = "select a file"


# init
# geometry="1024x600"
geometry="1350x700"
dt_string = datetime.now().strftime("%H:%M:%S")

session = HTMLSession()


# cont = 1
# while(cont):
#     infolist = fetchDatabase()
#     if infolist is None: 
#         print("fetch is void")    
#     else:
#         parseData(infolist)
#     print("------------------------------------------------------------")
#     time.sleep(REFRESH_PERIOD)

root = tk.Tk()
root.title("Race Tracker")
root.geometry(geometry)
# root.bind("<Configure>", getgeom)

nb = ttk.Notebook(root)   # Création du systeme d'onglets
nb.pack(fill=BOTH,expand=1)
defaultbg = root.cget('bg')  #  #d9d9d9

# cosmetic details
font_def    = tkFont.Font(family='Helvetica', size=12)
font_header = tkFont.Font(family='Helvetica', size=12, weight='bold') #weight='bold'
font_but1   = tkFont.Font(family='Helvetica', size=11, weight='bold') #weight='bold'
font_title  = tkFont.Font(family='Helvetica', size=16, weight='bold')
font_subtitle  = tkFont.Font(family='Helvetica', size=13, weight='bold')
font_ital   = tkFont.Font(family='Helvetica', size=10, slant='italic')

color="#a6e0c6"
optionsH = {'font': font_header, 'bg': "#a6e0c6", 'bd': 1, 'relief': 'groove' }
optionsC = {'font': font_def, 'bd': 1, 'relief': 'groove' }
optionsDescr = {'font': font_def, 'bd': 1, 'relief': 'groove', 'anchor': 'w' }

# Panels creation
# -----------------------------------------------
widgets = {} 
widgets['pilotStat'] = {}       # status widgets
widgets['pilotRTim'] = {}       # refresh date widgets
widgets['dateLabel'] = {} 
widgets['saveButtonParam'] = {} 
widgets['paramTab'] = {}
widgets['filesel'] = {}
widgets['strvar'] = {}

loadParams()
print("current params")
print(params)
createParametersPanel(nb)
# createPilotsPanel(nb)
root.update()

# Start recurrent process
# -----------------------------------------------
# generalUpdater()

root.mainloop()




