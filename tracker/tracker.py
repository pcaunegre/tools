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

# 
# requires:
#   
#    sudo apt-get install python3-tk
#    sudo apt install mpg321
#    sudo apt install msmtp
# 
#    pip3 install requests_html
#    pip3 install tplinkrouterc6u
# 




import sys
import os
from datetime import datetime
import time
import csv
import json
import re
from math import *
try:
    from requests_html import HTMLSession
except:
    print("requests_html lib missing\nplease run:\n   pip3 install requests_html")
    exit(0)
    
    
try:
    from tkinter import *
    from tkinter import ttk
    from tkinter import filedialog
    from tkinter import simpledialog
    import tkinter as tk
    import tkinter.font as tkFont
except:
    print("tkinter lib missing\nplease run:\n   sudo apt-get install python3-tk")
    exit(0)


# ------------------------------------------------------------------------------
# load pilot list from input csv file
# ------------------------------------------------------------------------------
def loadPilotList():
    
    global FILES, PilotsFilter
    
    PilotsFilter = {}
    if getParam('Filtrage') != 'Fichier':
        printlog("not using pilot list to filter")
        return()
        
    if FILES['pilotsFilter']=='' or FILES['pilotsFilter']=='select a file' or not os.path.isfile(FILES['pilotsFilter']):
        printlog("pilot list undefined or missing")
        return()
    
    with open(FILES['pilotsFilter'], newline='') as csvfile:
        reader = csv.DictReader(csvfile)
        for row in list(reader):
            PilotsFilter[row['Pseudo']]={"Name": row['Prenom'], "Surname": row['Nom']}
        csvfile.close()
    
    printlog(PilotsFilter)



# ------------------------------------------------------------------------------
# get info from FFVL tracker database
# ------------------------------------------------------------------------------
def fetchDatabase():
    
    now = int(time.time()-60); # take position from last minute 
    url = getParam('ffvl_url')+str(now)

    try:
        ret = session.get(url)
    except:
        printlog('Request failure')
        return('')
    htmlContent = ret.content.decode('utf-8')
            
    l = json.loads(htmlContent)
    return(l)


# ------------------------------------------------------------------------------
# parse data from database
# update status for each pilot
# ------------------------------------------------------------------------------
def parseData(infolist):
    
    global PilotsStatus, PilotsFilter
    alarm = 0
    
    # 1. recording pilot info from data received
    for elem in infolist:
        el = infolist[elem]
        pseudo=el['pseudo']
        (toofar,distkm) = isPilotTooFar(el)
        
        # filtering
        if getParam('Filtrage') == 'Fichier':
            # is this pilot in list ?
            if not (pseudo in PilotsFilter): 
                printlog(pseudo+" not in my list")
                continue
        
        elif getParam('Filtrage') == 'Distance':
            # is this pilot close enough ?
            if toofar: continue
            
        # create new item if needed
        if pseudo not in PilotsStatus: 
            name='-'; surname='-'
            # infos coming from filter file
            printlog("==  ITEM  NEW===============================")
            printlog(el)
            if pseudo in PilotsFilter:
                name = PilotsFilter[pseudo]['Name']
                surname = PilotsFilter[pseudo]['Surname']
            if 'last_h_speed' in el:
                speed = int(el['last_h_speed'])
            else:
                speed = '-'
            pilot = { "Name": name, "Surname": surname, "Cleared": 0, "Landed": 0, "TakeOff": 0,\
                "last_alt": int(el['last_altitude']), "last_lat": el['last_latitude'], \
                "last_lon": el['last_longitude'], "last_dist": 0, "last_h_speed": speed,\
                "d2atter": distkm,\
                "STtext": "-",\
                "STcolor": defaultbg,\
                "DTlog": "-",\
                "DTcolor": defaultbg,\
                "last_postime": el['last_position_utc_timestamp_unix'], "new": 1}
        
        # update an existing item
        else:
            pilot = PilotsStatus[pseudo]
        
            # evaluate status of this pilot
            printlog("==  ITEM  ==================================")
            printlog(el)
            (pilot) = updatePilotInfo(pilot,el)
        
        # recording
        PilotsStatus[pseudo] = pilot


    # 2. now review all pilots shown in table to evaluate warnings
    for p in PilotsStatus:
        (pilot,al) = checkPilot(PilotsStatus[p])
        PilotsStatus[p] = pilot
        alarm += al


    # save infos in backup file
    savePilotTable()
    
    # TO BE REVIEWED
    if alarm: 
        if getParam('AlerteSonore')=="1": sendSoundAlert()
        if getParam('AlerteSMS')=="1":    sendSmsAlert()
        if getParam('AlerteEmail')=="1":  sendEmailAlert()
        
    

# ------------------------------------------------------------------------------
# Accessories to send alert
# ------------------------------------------------------------------------------
def sendSoundAlert():
    print("sendSoundAlert")
    command=getParam('soundCmd')+execpath+"/sound.mp3"
    print(command)
    os.system(command)    
    
# ------------------------------------------------------------------------------
def sendSmsAlert(mess):
    numlist=getParam('TelPourAlerte').split(' ')
    try:
        from tplinkrouterc6u import (
            TplinkRouterProvider,
            TplinkRouter,
            TplinkC1200Router,
            TPLinkMRClient,
            TPLinkDecoClient,
            Connection
        )
        from logging import Logger
    except:
        print('Cannot work with TPLink router for sending SMS')
        return()

    try:
        router = TplinkRouterProvider.get_client('192.168.1.1','tplPc1unegr-')
        router.authorize()
        for num in numlist:
            print("sendSmsdAlert to: "+num)
            router.send_sms(num,mess)
        router.logout()
    except:
        print('Cannot work with TPLink router for sending SMS')
    
       

# ------------------------------------------------------------------------------
def sendEmailAlert(mess):
    print("sendEmailAlert")
    from email.message import EmailMessage
    from email.utils import make_msgid
    for dest in getParam('EmailPourAlerte').split(' '):
        horl = datetime.now()
        dt_string = horl.strftime("%H:%M:%S")
        mfile = "/tmp/msg"+dt_string
        message = "To: " + dest + "\n"
        message += "Subject: " + mess + "\n"
        message += mess + "\n"
        f = open(mfile,'w')
        print(message, file=f)
        f.close()
        command="cat " + mfile + " | msmtp " + dest + " "
        print("Email command: %s" % command)
        os.system(command)


# ------------------------------------------------------------------------------
# update info of a pilot
# ps : info list of pilot
# cur: current position
# 
# TakeOff : take off or not
# Landed  : has landed (no more moving after take off)
# 
# ------------------------------------------------------------------------------
def updatePilotInfo(ps,cur):
    
    tof = 0; lan = 0; 
    # rough distance calculation (in meter) from gps dec coord and altitude    
    distm = calcDistm(ps['last_lat'], ps['last_lon'], ps['last_alt'], \
        cur['last_latitude'], cur['last_longitude'], cur['last_altitude'])
    printlog("Step= "+str(distm))
    
    deltaTime=int(cur['last_position_utc_timestamp_unix'])-int(ps['last_postime'])
    printlog("DeltaT= "+str(deltaTime))

    if ps['new']:            
        #first log, do not check.
        ps.update({"new": 0})
        printlog("first log, skip check")
        deltat = "-"
        DTcolor = defaultbg
        STtext="-"
        STcolor = defaultbg
    else:   
        if deltaTime==0:
            printlog("log not new, skip check")
        else:
            # if speed is available, use speed to detect takeoff           
            if 'last_h_speed' in cur:
                
                last_h_speed = int(cur['last_h_speed'])
                ps.update({"last_h_speed": last_h_speed})
                printlog("Speed= "+str(last_h_speed))
                # detect takeoff: speed of 10km/h
                if ps['TakeOff']==0:
                    if (last_h_speed > int(getParam('VitMinDeco'))): tof = 1
                        
            # in addition use distance from last record
            # detect takeoff: move of 10m
            if ps['TakeOff']==0:
                if (distm > int(getParam('StepMinDeco'))): tof = 1
            
            else:
                if (distm < int(getParam('StepMaxPose'))): lan = 1
                
                # sometimes step is null but speed is not
                if 'last_h_speed' in cur:
                    if last_h_speed > int(getParam('VitMinDeco')): lan = 0
            
            if tof:
                ps.update({'TakeOff': 1})
                printlog("Pilot TakeOff "+cur['pseudo'])
             
            if lan:

                ps.update({'Landed': 1})
                printlog("Pilot Landed "+cur['pseudo'])


    ps.update({  "last_lat": cur['last_latitude'],\
                 "last_lon": cur['last_longitude'],\
                 "last_dist": distm,\
                 "last_alt": int(cur['last_altitude']),\
                 "last_postime": cur['last_position_utc_timestamp_unix'] })
                 
                 
    return(ps)       


# -----------------------------------------------
# check a pilot 
# 
# -----------------------------------------------
def checkPilot(ps):


    alarm = 0
    # evaluate pilot or log time warnings            
    (STtext,STcolor,DTval,DTcolor) = calcStatus(ps)

    # pilot landed but not cleared
    if (ps['Landed'] and ps['Cleared']==0):
        printlog("ALARM ! Pilot "+cur['pseudo'])
        alarm = 1

    ps.update({  "DTlog": DTval,\
                 "DTcolor": DTcolor,\
                 "STtext": STtext,\
                 "STcolor": STcolor })

    return((ps,alarm))       


# -----------------------------------------------
# check whether pilot is close to the playground
# returns boolean + distance to landing
# -----------------------------------------------
def isPilotTooFar(elem):
   
    lat = getParam('Latitude').strip()
    lon = getParam('Longitude').strip() 
    if len(lon) and len(lat):
        distkm = calcDistKm(lat, lon, elem['last_latitude'], elem['last_longitude'])
        if distkm > float(getParam('MaxDistance')):
            printlog(elem['pseudo']+" pilot too far "+str(int(distkm)))
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
    
    global FILES, PilotsStatus
    
    if os.path.isfile(FILES['pilotsStatus']):
        with open(FILES['pilotsStatus'], 'r') as in_file:
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
    
    global FILES, PilotsStatus
    
    with open(FILES['pilotsStatus'], 'w') as out_file:
        json.dump(PilotsStatus, out_file, indent = 4, sort_keys=True)
        out_file.close()      
    
        
        
# -----------------------------------------------
# Calculate status
# -----------------------------------------------
def calcStatus(elem):

    print("Calc")
    print(elem)
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

    # delta time between now and last log
    now = int(time.time())  
    deltat = now-int(elem['last_postime'])
    color2 = defaultbg
    if (deltat > int(getParam('delaiLogMax'))): color2="yellow"
    
    return((status,color,deltat,color2))


# -----------------------------------------------
# clear pilot status
# -----------------------------------------------
def clearPilotStatus(p):   
    
    global PilotsStatus
    
    elem=PilotsStatus[p]        

    if elem['Cleared']:
        if elem['Landed']:
            elem['Cleared']=0
            elem['Landed']=0
        
    else:
        if elem['Landed']: elem['Cleared']=1
        else: elem['Landed']=1
    
    PilotsStatus[p]=elem
    updatePilotTable()
    savePilotTable()
        
# -----------------------------------------------
# locate pilot on map
# -----------------------------------------------
def locatePilot(p):   
    
    global PilotsStatus
    
    lat = PilotsStatus[p]['last_lat']
    lon = PilotsStatus[p]['last_lon']
    url = "https://www.spotair.mobi/?lat="+str(lat)+"&lng="+str(lon)+"&zoom=15&ltffvl"
    command = 'firefox  --new-window \"'+url+'\" &'
    printlog(command)    
    os.system(command)
    



# ----------------------------------------------------------
# 
# proc loadConfig
#   read from the config file
# 
# ----------------------------------------------------------
def loadConfig():

    global FILES, config

    f = FILES['config']
    if (os.path.isfile(f) and os.path.getsize(f)>0):
        # read the config file
        with open(f, 'r') as in_file:
            config = json.load(in_file)
            in_file.close()
    
    else:
        config = \
{
    "parameters": {
        "Filtrage": {
            "method": "radio",
            "list": ["Fichier", "Distance", "Aucun"],
            "descr": "Filtrage par fichier, par la distance a l'atterrissage, ou pas de filtre",
            "def": "Aucun",
            "value": "Aucun"
        },
        "MaxDistance": {
            "method": "entry",
            "descr": "Filtrage des pilotes a une distance inferieure a cette valeur en km",
            "def": "50",
            "value": "50"
        },
        "VitMinDeco": {
            "method": "entry",
            "descr": "Vitesse minimale pour detecter le deco (si vitesse reportee)",
            "def": "10",
            "value": "10"
        },
        "StepMinDeco": {
            "method": "entry",
            "descr": "Variation de position (en m) minimale pour detecter le mode vol",
            "def": "10",
            "value": "10"
        },
        "StepMaxPose": {
            "method": "entry",
            "descr": "Variation de position (en m) maximale pour detecter le mode sol",
            "def": "5",
            "value": "5"
        },
        "delaiLogMax": {
            "method": "entry",
            "descr": "Delai (s) depuis le dernier log au-dela duquel on emet un Warning",
            "def": "300",
            "value": "300"
        },
        "AlerteSonore": {
            "method": "chkb",
            "descr": "Emettre l'alerte par un son",
            "def": "0",
            "value": "0"
        },
        "AlerteSMS": {
            "method": "chkb",
            "descr": "Emettre l'alerte par un SMS",
            "def": "0",
            "value": "0"
        },
        "AlerteEmail": {
            "method": "chkb",
            "descr": "Emettre l'alerte par un email",
            "def": "0",
            "value": "0"
        },
        "TelPourAlerte": {
            "method": "entry",
            "descr": "Nos de Tel auxquels envoyer un SMS d'alerte",
            "def": "",
            "value": ""
        },
        "EmailPourAlerte": {
            "method": "entry",
            "descr": "Email(s) auxquels envoyer une alerte",
            "def": "",
            "value": ""
        },
        "RefreshPeriod": {
            "method": "entry",
            "descr": "Periode de recuperation des donnees de tracking (s)",
            "def"  : "60",
            "value": "60"
        },
        "Editeur": {
            "method": "entry",
            "descr": "Outil pour editer les fichiers texte",
            "def": "nedit",
            "value": "nedit"
        },
        "soundCmd": {
            "visib": 0,
            "descr": "Tool to play sound",
            "def": "mpg321 --frames 50 ",
            "value": "mpg321 --frames 50 "
        },
        "pilotfile": {
            "visib": 0,
            "descr": "Fichier csv des pilotes",
            "def": "select a file",
            "value": "select a file"
        },
        "ffvl_url": {
            "visib": 0,
            "descr": "URL data",
            "def"  : "https://data.ffvl.fr/api/?mode=json&key=79ef8d9f57c10b394b8471deed5b25e7&ffvl_tracker_key=all&from_utc_timestamp=",
            "value": "https://data.ffvl.fr/api/?mode=json&key=79ef8d9f57c10b394b8471deed5b25e7&ffvl_tracker_key=all&from_utc_timestamp="
        },
        "spot": {
            "visib": 0,
            "descr": "Pre-selection du spot",
            "def": "custom",
            "value": "custom"
        },
        "Latitude": {
            "visib": 0,
            "descr": "Latitude du spot",
            "def": "",
            "value": " "
        },
        "Longitude": {
            "visib": 0,
            "descr": "Longitude du spot",
            "def": "",
            "value": " "
        },
        "Altitude": {
            "visib": 0,
            "descr": "Altitude du spot",
            "def": "",
            "value": " "
        }
    },
    "spots": {
        "custom": {
            "Longitude":  "",
            "Latitude":  "",
            "Altitude":  "",
            "descr": "Spot custom"
        },    
        "Arbas Attero": {
            "Longitude":  0.904557,
            "Latitude":  42.990937,
            "Altitude":  420,
            "descr": "Atterrissage Arbas"
        },
        "Val Louron Attero": {
            "Longitude":  0.405442,
            "Latitude":  42.802246,
            "Altitude":  951,
            "descr": "Atterrissage VL"
        },
        "Doussard": {
            "Longitude":  6.222322,
            "Latitude":  45.781463,
            "Altitude":  466,
            "descr": "Atterrissage Anncey"
        },
        "Lumbin": {
            "Longitude":  5.906357,
            "Latitude":  45.302509,
            "Altitude":  230,
            "descr": "Atterrissage St Hil"
        }
    }
        }
    
# ----------------------------------------------------------
# 
# proc writeConfig
#   store confid into config file
# 
# ----------------------------------------------------------
def writeConfig():

    global FILES, config

    # write the status file
    with open(FILES['config'], 'w') as out_file:
        json.dump(config, out_file, indent = 4, sort_keys=True)
        out_file.close()

# -----------------------------------------------
# extract params from GUI and store them into
# the config table
# -----------------------------------------------   
def saveParam():   
    
    global config       

    for el in widgets['paramTab']:
        item = config['parameters'][el]
        item['value'] = widgets['paramTab'][el].get()  # extract value from object
        config['parameters'][el] = item
        print("par extract "+el+" = "+item['value'])
    
    writeConfig()
    
# -----------------------------------------------
# Utility to get a param value
#    if param is not saved, get default from config
# -----------------------------------------------   
def getParam(parname):   

    global config
    
    elem = config['parameters'][parname]
    val = elem['def']
    if len(elem['value']): val = elem['value']
    return(val)
    
# -----------------------------------------------
# fetch data and parse
# -----------------------------------------------
def fetchAndParse():

    printlog('\n' + '+'*50 + '\n')
    # begin to grab info
    infolist = fetchDatabase()
    if infolist is None: 
        printlog("fetch is void")    
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
    
    widgets['dateLabel'].configure(bg='red')
    root.update()
    fetchAndParse()
    updatePilotTable()
    widgets['dateLabel'].configure(bg='blue')
    root.after(int(getParam('RefreshPeriod'))*1000,generalUpdater)
    
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

        elif wtype=="chkb":
             # making a single check button in the cell
             self.sv = tk.StringVar()
             self.sv.set(defval)
             self.entry = tk.Checkbutton(self.master, text = "", variable = self.sv, width = w )
        
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
    widgets['canvas']=canv

    sb = Scrollbar(frame,orient='vertical', width=20, command=canv.yview)
    sb.pack(side='right',fill='y')

    canv.configure(yscrollcommand=sb.set)
    
    createPilotTable(canv)
    

# ------------------------------------------------------------------------------
# PILOT PANEL
# ------------------------------------------------------------------------------
# ------------------------------------------------------------------------------
# Create pilots table
# ------------------------------------------------------------------------------
def createPilotTable(parent):   
    
    global PilotsStatus
    
    # first create a scrollable container
    pilottabframe=tk.Frame(parent)
    parent.create_window((0,25), window=pilottabframe, anchor='nw')    
    widgets['panel']['pilot'] = pilottabframe

    lat = getParam('Latitude')
    lon = getParam('Longitude')   
    if len(lat) and len(lon): 
        distcol = 1
    else: 
        distcol = 0
    
    # header creation
    colInd=0
    for (header,width) in [['Pseudo',25], ['Prenom',15], ['Nom',15], ['Alti',10], \
            ['Step (m)',10], ['VitHz',7], ['Dist (km)',10],['Status',15], ['Dernier log',10], ['Clairance',10], ['Loc',10]]:
        Cell(parent,x=colInd,y=0, w=width, defval=header, options=optionsH)   
        colInd+=1
    
    # table body
    ### TBD: ordering pilot table
    rownbr=0
    for p in PilotsStatus:
        rownbr+=1
        elem=PilotsStatus[p]
        addLineInTable(rownbr, p, elem)
    widgets['panel']['rownb'] = rownbr    

    
# -----------------------------------------------
# Create line of the table
# -----------------------------------------------
def addLineInTable(rownbr, p, elem):   
    
    f = widgets['panel']['pilot']
        
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
    c=Cell(f, x=7,y=rownbr, w=15, defval=elem['STtext'],        options=optionsC, bgc=elem['STcolor'] ) 
    widgets['pilotStat'][p]=c   # keep an handle to change the status later
    c=Cell(f, x=8,y=rownbr, w=10, defval=elem['DTlog'],        options=optionsC, bgc=elem['DTcolor'] ) 
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

    for p in PilotsStatus:
        elem=PilotsStatus[p]
        
        if p in widgets['pilotStat']:
            # update existing line in the table
            widgets['pilotStat'][p].sv.set(elem['STtext'])             # change the content of this widget
            widgets['pilotStat'][p].entry.configure(bg=elem['STcolor'])   # change the color of this widget
            widgets['pilotRTim'][p].sv.set(elem['DTlog'])
            widgets['pilotRTim'][p].entry.configure(bg=elem['DTcolor'])
            widgets['pilotAlt'][p].sv.set(elem['last_alt'])
            widgets['pilotHs'][p].sv.set(elem['last_h_speed'])
            widgets['pilotStep'][p].sv.set(elem['last_dist'])
            widgets['pilotDist'][p].sv.set(elem['d2atter'])
        else:   
            # add a new line in the table
            rownbr = widgets['panel']['rownb']+1
            widgets['panel']['rownb'] = rownbr
            addLineInTable(rownbr, p, elem)

    maxscroll=widgets['panel']['rownb']*30
    widgets['canvas'].configure(scrollregion=(0, 0, 600, maxscroll))
        
# ------------------------------------------------------------------------------
# OPTIONS PANEL
# ------------------------------------------------------------------------------
# -----------------------------------------------
# Create content of parameters panel
# -----------------------------------------------
def createParametersPanel(nb):   
    
    global FILES, config
    
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
    Label(fileframe, relief='flat', bd=1, text="Fichier",width=15).pack(side='left')
    sv = tk.StringVar()
    FILES['pilotsFilter']=getParam('pilotfile')
    sv.set(FILES['pilotsFilter'])
    widgets['filesel']=sv
    widgets['paramTab']['pilotfile']=sv
    l=Label(fileframe, relief='sunken', bd=1, font=font_ital, textvariable=sv,width=80)
    l.pack(side='left')
    widgets['filelab']=l
    sf=Button(fileframe,relief='raised', bd=3,text="Select",height=1, command=selectFile)
    sf.pack(side='left')
    eb=Button(fileframe,relief='raised', bd=3,text="Editer",height=1, command=editFile)
    eb.pack(side='left')
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
    widgets['strvar']['ld'].set(getParam('spot'))
    widgets['paramTab']['spot'] = widgets['strvar']['ld']
    landsel = OptionMenu(menuframe, widgets['strvar']['ld'], *spotlist, command=updSpotEntry)
    landsel.config(width=25)    
    landsel.grid(column=2, row=1, padx=1, pady=1)
    svb=Button(menuframe,relief='raised', bd=3,text="Renommer",height=1, command=saveSpot)
    svb.grid(column=3, row=1, padx=1, pady=1)
       
    rwnbr = 1
    for item in ['Latitude', 'Longitude', 'Altitude']:
        rwnbr+=1
        widgets['strvar'][item] = tk.StringVar()
        widgets['paramTab'][item] = widgets['strvar'][item]
        Label(menuframe, relief='flat', bd=1, text=item,width=15).grid(column=1, row=rwnbr, padx=1, pady=1)
        ttk.Entry(menuframe, textvariable=widgets['strvar'][item], width=30).grid(column=2, row=rwnbr, padx=1, pady=1) 
        widgets['strvar'][item].set(getParam(item))
    
    
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
    
    global config
    
    # store this object for future destroy/refresh
    widgets['paramsparentframe']=parent
    
    # first create a container
    paramstabframe=tk.Frame(parent)
    parent.create_window((0,0), window=paramstabframe, anchor='nw')    

    valW = 40
    # Table headers creation
    Cell(paramstabframe,x=0, y=0, w=15, options=optionsH, defval='Parametre')   
    Cell(paramstabframe,x=1, y=0, w=valW, options=optionsH, defval='Valeur')   
    Cell(paramstabframe,x=2, y=0, w=100, options=optionsH, defval='Description')   

    options={'height': 2}

    # Table body creation
    rownbr = 0
    for name in config['parameters']:
        elem = config['parameters'][name]
        if (('visib' in elem) and (not elem['visib'])): continue
        rownbr += 1
        
        # automatic ordering fo parameters
        if 'rownb' in elem:
            row = elem['rownb']
        else:
            row = rownbr
            elem.update({'rownb': rownbr})
        
        Cell(paramstabframe,x=0,y=row,defval=name, w=15, options={'height': 2} )            # Id column
        
        value=elem['def']
        descrip = elem['descr']
        if len(str(value)):
            descrip = descrip + " (def. " + str(value) + ")"
            
        value = elem['value']
        if not len(value): value = elem['def']             
        met = elem['method']
        options={}
        if met=='scale':
            options={'length': 270}
            options['from_']=elem['from']
            options['to']=elem['to']
            options['resolution']=elem['res']
            c=Cell(paramstabframe,x=1,y=row,defval=value, w=valW, wtype='scale', options=options) # Status column
            widgets['paramTab'][name]=c.entry
       
        elif met=='radio':
            c=Cell(paramstabframe,x=1,y=row,defval=value, togvals=elem['list'], w=valW, wtype='radio', options=options) # Status column
            widgets['paramTab'][name]=c.sv   # 
        
        elif met=='chkb':
            c=Cell(paramstabframe,x=1,y=row,defval=value, w=valW, wtype='chkb', options=options) # Status column
            widgets['paramTab'][name]=c.sv   # 
        
        elif met=='entry':
            c=Cell(paramstabframe,x=1,y=row,defval=value, w=valW, wtype='ent', options=options) 
            widgets['paramTab'][name]=c.sv   # 

        elif met=='label':
            c=Cell(paramstabframe,x=1,y=row,defval=value, w=valW, wtype='lab', options=options) 
            widgets['paramTab'][name]=c.sv   # 

        elif wtype=="tog":
            # making a toggle button in the cell
            self.vallist = togvals.copy()
            self.vallist.append(togvals.pop(0))
            self.sv = tk.StringVar()
            self.sv.set(defval)
            self.entry = tk.Button(self.master, textvariable=self.sv, command=self.OnClick, width=17, text=defval, padx=0, pady=1.5)   #bg="red", fg="blue",
        
        Cell(paramstabframe,x=2,y=row,defval=descrip, options={'font': font_def, 'anchor': 'w'}, w=100) # Descr column


# -----------------------------------------------
# utility for spot selection
# -----------------------------------------------
def updSpotEntry(W):
    
    spot = widgets['strvar']['ld'].get()
    elem = getCoord(spot)
    for item in ['Latitude', 'Longitude', 'Altitude']:
        widgets['strvar'][item].set(elem[item])

# -----------------------------------------------
# utility for spot selection
# -----------------------------------------------
def saveSpot():
    
    global config
    
    userInput = simpledialog.askstring(title="Renommer ce spot",
                prompt="Nom du spot:")
       
    newspot = {}
    for item in ['Latitude', 'Longitude', 'Altitude']:
        value = widgets['strvar'][item].get()
        newspot[item] = value       
    
    widgets['strvar']['ld'].set(userInput)
    config['spots'][userInput] = newspot
    
    writeConfig()
    
    
# -----------------------------------------------
# utility for file selection
# -----------------------------------------------
def selectFile():

    global FILES
    
    ret = filedialog.askopenfilename()
    if len(ret):
        FILES['pilotsFilter'] = ret
        widgets['filesel'].set(ret)
        widgets['filelab'].configure(font=font_def)

# -----------------------------------------------
# utility for file editing
# -----------------------------------------------
def editFile():

    global FILES
    
    command = getParam('Editeur') + ' ' + FILES['pilotsFilter']
    os.system(command)


# -----------------------------------------------
# utility for drop down list
# -----------------------------------------------
def getSpotList():
    
    global config
    
    outlist = []
    for elem in config['spots']:
        outlist.append(elem)
    return(outlist)

# -----------------------------------------------
# return coord (lat lon alt) of a spot
# -----------------------------------------------
def getCoord(spot):
    
    global config
    
    if spot in config['spots']:
        return(config['spots'][spot])
    else:
        return()


# -----------------------------------------------
# manage log messages
# -----------------------------------------------
def printlog(mess):

    global FILES
    print(mess,file=FILES['logFD'], flush=True)
    print(mess, flush=True)
    
    
# -----------------------------------------------
# initiate working dirs
# -----------------------------------------------
def initDirs():
    
    global FILES
    
    toolHomeDir = os.environ['HOME'] + "/.config/tracker"
    logFile     = toolHomeDir + "/tracker.log"
    FILES = {}
    FILES['config']  = toolHomeDir + "/tracker.config"
    FILES['pilotsStatus'] = toolHomeDir + "/tracker.pilots"
    FILES['pilotsFilter'] = "select a file"

    # toolHomeDir
    if not os.path.isdir(toolHomeDir):
        print("toolHomeDir does not exist, creating : "+toolHomeDir)
        try: os.makedirs(toolHomeDir)
        except: 
            print("Cannot write to "+toolHomeDir)
            exit(1)
    else: print("toolHomeDir : "+toolHomeDir)

    FILES['logFD'] = open(logFile,'w')



# -----------------------------------------------
# -----------------------------------------------
# def getgeom(W):
#     
#     printlog("Geom")
#     printlog("The width of Tkinter window:", root.winfo_width())
#     printlog("The height of Tkinter window:", root.winfo_height())     
#     printlog("Screen")
#     printlog("The width of Tkinter window:", root.winfo_screenwidth())
#     printlog("The height of Tkinter window:", root.winfo_screenheight())     





    
# ------------------------------------------------------------------------------
# ------------------------------------------------------------------------------
# -----------------------------
#   MAIN PROGRAM
# -----------------------------
# ------------------------------------------------------------------------------
# ------------------------------------------------------------------------------
# def
execpath=os.path.dirname(sys.argv[0])

# init
initDirs()

dt_string = datetime.now().strftime("%H:%M:%S")
printlog('='*80+'\nStarting '+dt_string)

geometry = "1400x700"
root = tk.Tk()
root.title("Race Tracker")
root.geometry(geometry)
# root.bind("<Configure>", getgeom)

nb = ttk.Notebook(root)   # Creation du systeme d'onglets
nb.pack(fill=BOTH,expand=1)

# cosmetic details
defaultbg = root.cget('bg')  #  #d9d9d9
font_def    = tkFont.Font(family='Helvetica', size=12)
font_header = tkFont.Font(family='Helvetica', size=12, weight='bold') #weight='bold'
font_but1   = tkFont.Font(family='Helvetica', size=11, weight='bold') #weight='bold'
font_title  = tkFont.Font(family='Helvetica', size=16, weight='bold')
font_subtitle  = tkFont.Font(family='Helvetica', size=13, weight='bold')
font_ital   = tkFont.Font(family='Helvetica', size=10, slant='italic')

color = "#a6e0c6"
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
widgets['canvas'] = {}

loadConfig()

session = HTMLSession()

createParametersPanel(nb)

root.update()

root.mainloop()




