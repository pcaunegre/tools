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
REFRESH_PERIOD = 60
# REFRESH_PERIOD = 10

# ------------------------------------------------------------------------------
# load pilot list from input csv file
# ------------------------------------------------------------------------------
def loadPilotList():
    
    global PILOT_FILTER, params
    PILOT_FILTER = {}
    if params['Filtrage'] != 'Fichier':
        print("not using pilot list to filter",file=logfile, flush=True)
        return()
        
    if PILOTS_FILE=='' or PILOTS_FILE=='select a file' or not os.path.isfile(PILOTS_FILE):
        print("pilot list undefined or missing",file=logfile, flush=True)
        return()
    
    with open(PILOTS_FILE, newline='') as csvfile:
        reader = csv.DictReader(csvfile)
        for row in list(reader):
            PILOT_FILTER[row['Pseudo']]={ "Name": row['Prenom'], "Surname": row['Nom']}
        csvfile.close()
    
    print(PILOT_FILTER,file=logfile, flush=True)



# ------------------------------------------------------------------------------
# get info from database
# ------------------------------------------------------------------------------
def fetchDatabase():
    
    now = int(time.time()-60); # take position from last minute 
    url =FFVL_URL+str(now)
#     print("URL=%s" % url,file=logfile, flush=True)
    try:
        ret = session.get(url)
    except:
        print('Request failure',file=logfile, flush=True)
        return('')
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
    
    global PilotsStatus, params, PILOT_FILTER
    alarm = 0
    for elem in infolist:
        el = infolist[elem]
        pseudo=el['pseudo']
        (toofar,distkm) = isPilotTooFar(el)
        
        # filtering
        if params['Filtrage'] == 'Fichier':
            # is this pilot in list ?
            if not (pseudo in PILOT_FILTER): 
                print("%s not in my list" % pseudo,file=logfile, flush=True)
                continue
        
        elif params['Filtrage'] == 'Distance':
            # is this pilot close enough ?
            if toofar: continue
            
        # create new item if needed
        if pseudo not in PilotsStatus: 
            name='-'; surname='-'
            # infos coming from filter file
            print("==  ITEM  NEW===============================",file=logfile, flush=True)
            print(el,file=logfile, flush=True)
            if pseudo in PILOT_FILTER:
                name = PILOT_FILTER[pseudo]['Name']
                surname = PILOT_FILTER[pseudo]['Surname']
            if 'last_h_speed' in el:
                speed = int(el['last_h_speed'])
            else:
                speed = '-'
            pilot = { "Name": name, "Surname": surname, "Cleared": 0, "Landed": 0, "TakeOff": 0,\
                "last_alt": int(el['last_altitude']), "last_lat": el['last_latitude'], \
                "last_lon": el['last_longitude'], "last_dist": 0, "last_h_speed": speed,\
                "d2atter": distkm,\
                "last_postime": el['last_position_utc_timestamp_unix'], "new": 1}
        
        else:
            pilot = PilotsStatus[pseudo]
        
            # evaluate status of this pilot
            print("==  ITEM  ==================================",file=logfile, flush=True)
            print(el,file=logfile, flush=True)
            (pilot,al) = checkPilot(pilot,el)
            alarm += al
        
        # recording
        PilotsStatus[pseudo] = pilot

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
    distm = calcDistm(ps['last_lat'], ps['last_lon'], ps['last_alt'], \
        cur['last_latitude'], cur['last_longitude'], cur['last_altitude'])
    print("Step= %d m" % distm,file=logfile, flush=True)
    
    deltaTime=int(cur['last_position_utc_timestamp_unix'])-int(ps['last_postime'])
    print("DeltaT= %d s" % deltaTime,file=logfile, flush=True)

    if ps['new']:            
        #first log, do not check.
        ps.update({"new": 0})
        print("first log, skip check",file=logfile, flush=True)
    else:   
        if deltaTime==0:
            print("log not new, skip check",file=logfile, flush=True)
        else:
            # if speed is available, use speed to detect takeoff
            if 'last_h_speed' in cur:
                
                last_h_speed = int(cur['last_h_speed'])
                ps.update({"last_h_speed": last_h_speed})
                print("Speed= %d km/h" % last_h_speed,file=logfile, flush=True)
                # detect takeoff: speed of 10km/h
                if ps['TakeOff']==0:
                    if (last_h_speed > int(params['VitMinDeco'])): tof = 1
                        
            # in addition use distance from last record
            # detect takeoff: move of 10m
            if ps['TakeOff']==0:
                if (distm > int(params['DistMinDeco'])): tof = 1
            
            else:
                if (distm < int(params['DistMaxPose'])): lan = 1
                
                # sometimes step is null but speed is not
                if 'last_h_speed' in cur:
                    if last_h_speed > int(params['VitMinDeco']): lan = 0
            
            if tof:
                ps.update({'TakeOff': 1})
                print("Pilot %s takeoff V" % cur['pseudo'],file=logfile, flush=True)
             
            if lan:
                ps.update({'Landed': 1})
                print("Pilot %s landed" % cur['pseudo'],file=logfile, flush=True)

            # pilot landed but not cleared
            if (ps['Landed'] and ps['Cleared']==0):
                print("ALARM ! Pilot %s" % cur['pseudo'],file=logfile, flush=True)
                alarm = 1
        

    ps.update({  "last_lat": cur['last_latitude'],\
                 "last_lon": cur['last_longitude'],\
                 "last_dist": distm,\
                 "last_alt": int(cur['last_altitude']),\
                 "last_postime": cur['last_position_utc_timestamp_unix']})
    return((ps,alarm))       

# -----------------------------------------------
# check whether pilot is close to the playground
# returns boolean + distance to landing
# -----------------------------------------------
def isPilotTooFar(elem):
   
    global params
    lat = params['Latitude']
    lon = params['Longitude']    
    if len(lon) and len(lat):
        distkm = calcDistKm(lat, lon, elem['last_latitude'], elem['last_longitude'])
        if distkm > float(params['MaxDistance']):
            print("%s pilot too far %d" % (elem['pseudo'], int(distkm)),file=logfile, flush=True)
            return((1,distkm))
        else:
            return((0,distkm))
    else:
        # center point not defined, so no filtering
        return((0,"-"))

 
# -----------------------------------------------
# distance calc between 2 gps coordinates
# in decimal degrees and z in meter, for small distances
# return in m
# -----------------------------------------------
def calcDistm(x1,y1,z1,x2,y2,z2):

    k1 = 111000           # 1 deg is roughly 111km
    k2 = 111000*cos(6.3*float(x1)/360)   # 1 deg is roughly 111km at equator
    dist= sqrt(\
        ((float(x1)-float(x2))*k1)**2 +\
        ((float(y1)-float(y2))*k2)**2 +\
         (float(z1)-float(z2))**2 )
    return(int(dist))


# -----------------------------------------------
# distance calc between 2 lat/lon coordinates
# in decimal degrees, for long distance
# return in km
# -----------------------------------------------
def calcDistKm(x1,y1,x2,y2):

    R = 6373.0
    lat1 = radians(float(x1))
    lon1 = radians(float(y1))
    lat2 = radians(float(x2))
    lon2 = radians(float(y2))
    dlon = lon2 - lon1
    dlat = lat2 - lat1
    a = sin(dlat / 2)**2 + cos(lat1) * cos(lat2) * sin(dlon / 2)**2
    c = 2 * atan2(sqrt(a), sqrt(1 - a))
    distance = R * c
    return(int(distance))
    
# -----------------------------------------------
# load pilot table from backup file
# -----------------------------------------------
def loadPilotTable():   
    
    global PilotsStatus
    if os.path.isfile(PILOTS_STATUS):
        with open(PILOTS_STATUS, 'r') as in_file:
            content = in_file.read()
            in_file.close()
            if len(content):
                PilotsStatus = json.loads(content)
            else:
                PilotsStatus = {}
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
        
# -----------------------------------------------
# locate pilot on map
# -----------------------------------------------
def locatePilot(p):   
    
    global PilotsStatus
    lat = PilotsStatus[p]['last_lat']
    lon = PilotsStatus[p]['last_lon']
    url = "https://www.spotair.mobi/?lat="+str(lat)+"&lng="+str(lon)+"&zoom=15"
    command = 'firefox  --new-window \"'+url+'\"'
    print(command,file=logfile, flush=True)    
    os.system(command)
    
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
#     widgets['saveButtonParam'].configure(bg=defaultbg)


# -----------------------------------------------
# fetch data and parse
# -----------------------------------------------
def fetchAndParse():

    print("\n++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++\n",file=logfile, flush=True)
    # begin to grab info
    infolist = fetchDatabase()
    if infolist is None: 
        print("fetch is void",file=logfile, flush=True)    
    else:
        # filter and parse data
        parseData(infolist)

# -----------------------------------------------
# Manage starting process
# -----------------------------------------------
def processStart():
    
    saveParam()
    
    #1. load the pilot filter (if any)
    loadPilotList()
    
    #2. load the pilot status (if any) in case of restart after a crash
    loadPilotTable()
        
#     #3. begin to grab info
#     fetchAndParse()    
    
    #4. create pilot table and open panel
    createPilotsPanel(nb)
    nb.select(1)  
    
    #5. start the recurrent updater
    generalUpdater()

# -----------------------------------------------
# Recurrent process
# -----------------------------------------------
def generalUpdater():   
    
    fetchAndParse()
    updatePilotTable()
    root.after(REFRESH_PERIOD*1000,generalUpdater)
    
# -----------------------------------------------
# reset pilot status file
# -----------------------------------------------
def resetPilotStatus ():
    
    global PilotsStatus
    PilotsStatus = {}
    savePilotTable()  
    
    
       
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
#             self.entry.bind("<ButtonRelease-1>", self.ValueChanged)                   
        
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
#                 b = Radiobutton(self.entry, variable=self.sv, text=butt, command=self.ValueChanged, value=butt, font=font_def)
                b = Radiobutton(self.entry, variable=self.sv, text=butt,  value=butt, font=font_def)
                b.pack(side='left', expand=1)    
#             self.entry.bind("<ButtonRelease-1>", self.ValueChanged)                   

        elif wtype=="clearb":
            # making a single push button in the cell
             self.entry = tk.Button(self.master, command=self.OnPush, width=w, text=defval , padx=1, pady=1, bd=1)   #bg="red", fg="blue",
        
        elif wtype=="locb":
            # making a single push button in the cell
             self.entry = tk.Button(self.master, command=self.Locate, width=w, text=defval , padx=1, pady=1, bd=1)   #bg="red", fg="blue",

        self.entry.grid(column=self.x, row=self.y, padx=1, pady=1)

    def OnPush(self):
        clearPilotStatus(self.pid)
        
    def Locate(self):
        locatePilot(self.pid)
        
#     def ValueChanged(self,newval=''):
#         widgets['saveButtonParam'].configure(bg='Yellow')        

    def OnClick(self):
        curval=self.sv.get()
        indx=self.vallist.index(curval)
        newval=self.vallist[indx+1]
        self.sv.set(newval)
        self.ValueChanged()
        

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
    

# ------------------------------------------------------------------------------
# PILOT PANEL
# ------------------------------------------------------------------------------
# ------------------------------------------------------------------------------
# Create pilots panel
# ------------------------------------------------------------------------------
def createPilotTable(parent):   
    
    global PilotsStatus
    
    # first create a scrollable container
    pilottabframe=tk.Frame(parent)
    parent.create_window((0,0), window=pilottabframe, anchor='nw')    
    widgets['panel']['pilot'] = pilottabframe

    lat = params['Latitude']
    lon = params['Longitude']    
    if len(lat) and len(lon): 
        distcol = 1
    else: 
        distcol = 0
    
    # header creation
    colInd=0
    for (header,width) in [['Pseudo',25], ['Prenom',15], ['Nom',15], ['ALT',10], \
            ['Step',10], ['VitHz',7], ['Dist',10],['Status',15], ['Dernier log',10], ['Clear',10], ['Loc',10]]:
        Cell(pilottabframe,x=colInd,y=0, w=width, defval=header, options=optionsH)   
        colInd+=1
    
    # table body
    rownbr=0
    for p in PilotsStatus:
        rownbr+=1
        elem=PilotsStatus[p]
        addLineInTable(rownbr, p, elem)
    widgets['panel']['rownb'] = rownbr    

    
# -----------------------------------------------
# Create pilots table
# -----------------------------------------------
def addLineInTable(rownbr, p, elem):   
    
    f = widgets['panel']['pilot']
    now = int(time.time())
    deltat = now-int(elem['last_postime'])
    (status,color) = calcStatus(elem)
    Cell(f, x=0,y=rownbr, w=25, defval=p,               options=optionsC, bgc=defaultbg) 
    Cell(f, x=1,y=rownbr, w=15, defval=elem['Name'],    options=optionsC, bgc=defaultbg ) 
    Cell(f, x=2,y=rownbr, w=15, defval=elem['Surname'], options=optionsC, bgc=defaultbg ) 
    c=Cell(f, x=3,y=rownbr, w=10, defval=elem['last_alt'], options=optionsC, bgc=defaultbg ) 
    widgets['pilotAlt'][p]=c   # keep an handle to change the status later
    c=Cell(f, x=4,y=rownbr, w=10, defval=elem['last_dist'], options=optionsC, bgc=defaultbg ) 
    widgets['pilotStep'][p]=c   # keep an handle to change the status later
    c=Cell(f, x=5,y=rownbr, w=7, defval=elem['last_h_speed'], options=optionsC, bgc=defaultbg ) 
    widgets['pilotHs'][p]=c   # keep an handle to change the status later
    c=Cell(f, x=6,y=rownbr, w=10, defval=elem['d2atter'], options=optionsC, bgc=defaultbg ) 
    widgets['pilotDist'][p]=c   # keep an handle to change the status later
    c=Cell(f, x=7,y=rownbr, w=15, defval=status,        options=optionsC, bgc=color ) 
    widgets['pilotStat'][p]=c   # keep an handle to change the status later
    c=Cell(f, x=8,y=rownbr, w=10, defval=deltat,        options=optionsC, bgc=defaultbg ) 
    widgets['pilotRTim'][p]=c
    Cell(f, x=9,y=rownbr, w=10, wtype="clearb",defval="Clear/Undo",pid=p, options=optionsC, bgc=defaultbg ) 
    Cell(f, x=10,y=rownbr, w=10, wtype="locb",defval="Voir",pid=p, options=optionsC, bgc=defaultbg ) 

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
        if p in widgets['pilotStat']:
            # update existing line in the table
            widgets['pilotStat'][p].sv.set(status)             # change the content of this widget
            widgets['pilotStat'][p].entry.configure(bg=color)   # change the color of this widget
            widgets['pilotRTim'][p].sv.set(deltat)
            widgets['pilotRTim'][p].sv.set(deltat)
            widgets['pilotAlt'][p].sv.set(elem['last_alt'])
            widgets['pilotHs'][p].sv.set(elem['last_h_speed'])
            widgets['pilotStep'][p].sv.set(elem['last_dist'])
            widgets['pilotDist'][p].sv.set(elem['d2atter'])
        else:   
            # add a new line in the table
            rownbr = widgets['panel']['rownb']+1
            widgets['panel']['rownb'] = rownbr
            addLineInTable(rownbr, p, elem)

        
# ------------------------------------------------------------------------------
# OPTIONS PANEL
# ------------------------------------------------------------------------------
# -----------------------------------------------
# Create content of parameters panel
# -----------------------------------------------
def createParametersPanel(nb):   
    
    global PILOTS_FILE, params
    frame=ttk.Frame(nb)
    frame.pack()
    nb.add(frame, text="Parametres", padding='2mm')
    
    # - start and reset buttons section
    buttonframe=tk.Frame(frame, relief='raised', height=10)
    buttonframe.pack(side='top',fill='both', expand=0)
    sb=Button(buttonframe, bd=3, highlightcolor='yellow',text="START !",height=1,width=20, command=processStart)
    sb.pack(side='left')
    rb=Button(buttonframe, bd=3, highlightcolor='yellow',text="Reset",height=1,width=20, command=resetPilotStatus)
    rb.pack(side='left')
    Label(frame, relief='groove', bd=0).pack(side='top')        # spacer
    
    # - file section
    Label(frame, relief='groove', font=font_subtitle, bd=1, bg='#d9d98c',anchor='w', text="Fichier pilotes ",width=1000).pack(side='top')
    Label(frame, font=font_def,relief='flat', bd=3,anchor='w',fg='blue', text="Ce fichier facultatif liste les pilotes a filtrer( fichier .csv contenant : Pseudo,Nom,Prenom). ",width=1000).pack(side='top')
    fileframe=tk.Frame(frame, relief='raised', height=20)
    fileframe.pack(side='top',fill='both', expand=0)
    Label(fileframe, relief='flat', bd=1, text="Fichier pilote",width=15).pack(side='left')
    sv = tk.StringVar()
    if 'pilotfile' in params: PILOTS_FILE=params['pilotfile']
    sv.set(PILOTS_FILE)
    widgets['filesel']=sv
    widgets['paramTab']['pilotfile']=sv
    if 'pilotfile' in params: PILOTS_FILE=params['pilotfile']
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
    widgets['strvar']['ld'] = tk.StringVar()
    widgets['strvar']['ld'].set(spotlist[0])
    if 'spot' in params: widgets['strvar']['ld'].set(params['spot'])
    widgets['paramTab']['spot'] = widgets['strvar']['ld']
    landsel = OptionMenu(menuframe, widgets['strvar']['ld'], *spotlist, command=updSpotEntry)
    landsel.config(width=25)    
    landsel.grid(column=2, row=1, padx=1, pady=1)
    rwnbr = 1
    for item in ['Latitude', 'Longitude', 'Altitude']:
        rwnbr+=1
        widgets['strvar'][item] = tk.StringVar()
        widgets['paramTab'][item] = widgets['strvar'][item]
        Label(menuframe, relief='flat', bd=1, text=item,width=15).grid(column=1, row=rwnbr, padx=1, pady=1)
        ttk.Entry(menuframe, textvariable=widgets['strvar'][item], width=30).grid(column=2, row=rwnbr, padx=1, pady=1) 
        if item in params: widgets['strvar'][item].set(params[item])
    
    # - options section
    Label(frame, relief='groove', font=font_subtitle, bd=1, bg='#d9d98c',anchor='w', text="Options",width=1000).pack(side='top')
#     b=Button(frame,bd=3,text="Sauvegarder",height=10, command=saveParam)
#     b.pack(side='right')
#     widgets['saveButtonParam']=b

    canv = Canvas(frame, width=600, height=300, scrollregion=(0, 0, 600, 1200))
    canv.pack(side='left',fill='both', expand=1)

    sb = Scrollbar(frame,orient='vertical', width=20, command=canv.yview)
    sb.pack(side='right',fill='y')

    canv.configure(yscrollcommand=sb.set)
    
    createParamsTable(canv)

#TBR: saving of file, distance infos
 

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
    rownbrr=1
    for elem in config['parameters']:
        name=elem['name']
        Cell(paramstabframe,x=0,y=rownbrr,defval=name, w=15, options={'height': 2} )            # Id column
        
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
            c=Cell(paramstabframe,x=1,y=rownbrr,defval=value, w=30, wtype='scale', options=options) # Status column
            widgets['paramTab'][name]=c.entry
       
        elif met=='radio':
            c=Cell(paramstabframe,x=1,y=rownbrr,defval=value, togvals=elem['list'], w=30, wtype='radio', options=options) # Status column
            widgets['paramTab'][name]=c.sv   # 
        
        elif met=='entry':
            c=Cell(paramstabframe,x=1,y=rownbrr,defval=value, w=30, wtype='ent', options=options) 
            widgets['paramTab'][name]=c.sv   # 

        elif met=='label':
            c=Cell(paramstabframe,x=1,y=rownbrr,defval=value, w=30, wtype='lab', options=options) 
            widgets['paramTab'][name]=c.sv   # 

        elif wtype=="tog":
            # making a toggle button in the cell
            self.vallist = togvals.copy()
            self.vallist.append(togvals.pop(0))
            self.sv = tk.StringVar()
            self.sv.set(defval)
            self.entry = tk.Button(self.master, textvariable=self.sv, command=self.OnClick, width=17, text=defval, padx=0, pady=1.5)   #bg="red", fg="blue",
        
        Cell(paramstabframe,x=2,y=rownbrr,defval=descrip, options={'font': font_def, 'anchor': 'w'}, w=100) # Descr column
        rownbrr+=1


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











def getgeom(W):
    
    print("Geom")
    print("The width of Tkinter window:", root.winfo_width())
    print("The height of Tkinter window:", root.winfo_height())     
#     print("Screen")
#     print("The width of Tkinter window:", root.winfo_screenwidth())
#     print("The height of Tkinter window:", root.winfo_screenheight())     
    
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
logfile         = os.environ['HOME']+"/.tracker.log"
PILOTS_STATUS   = os.environ['HOME']+"/.tracker.pilots"
PILOTS_FILE     = "select a file"

logfile = open(logfile,'w')


# init
dt_string = datetime.now().strftime("%H:%M:%S")

geometry="1400x700"
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
widgets['pilotStat']= {}       # status widgets
widgets['pilotRTim']= {}       # refresh date widgets
widgets['pilotAlt'] = {} 
widgets['pilotHs']  = {} 
widgets['pilotStep']= {} 
widgets['pilotDist']= {}
widgets['panel']    = {} 
widgets['dateLabel'] = {} 
# widgets['saveButtonParam'] = {} 
widgets['paramTab'] = {}
widgets['filesel'] = {}
widgets['strvar'] = {}

session = HTMLSession()

loadParams()
print("current params",file=logfile, flush=True)
print(params,file=logfile, flush=True)
createParametersPanel(nb)

root.update()

# Start recurrent process
# -----------------------------------------------
# generalUpdater()

root.mainloop()




