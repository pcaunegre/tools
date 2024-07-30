#!/usr/bin/python3

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
import time
import csv
import json
import re
from requests_html import HTMLSession
from math import *

FFVL_URL="https://data.ffvl.fr/api/?mode=json&key=79ef8d9f57c10b394b8471deed5b25e7&ffvl_tracker_key=all&from_utc_timestamp="
REFRESH_PERIOD = 60
PILOTS_FILE = "pilots.csv"
PILOTS_STATUS = "pilots.status"

# ------------------------------------------------------------------------------
# load pilot list from input csv file
# preset the table PilotsStatus and stores in a backup file
# initial storage of that table in a backup file (json format)
# ------------------------------------------------------------------------------
def loadPilotList():
    global PilotsStatus

    if os.path.isfile(PILOTS_STATUS):
        
        print("Reloading session")
        # session reload (already initialized)
        with open(PILOTS_STATUS, 'r') as in_file:
            PilotsStatus = json.load(in_file)
            in_file.close()
                
    elif os.path.isfile(PILOTS_FILE):
        
        # initialize session by loading input file
        print("Initializing session")
        PilotsStatus = {}
        with open(PILOTS_FILE, newline='') as csvfile:
            reader = csv.DictReader(csvfile)
            for row in list(reader):
                print(row['Nom'])
                stoelem = { "Name": row['Prenom'], "Surname": row['Nom'], "TakeOff": 0, "Landed": 0, "Standing": 0, "Cleared": 0, "last_h_speed": 0,"last_lat": 0,"last_lon": 0, "last_alt": 0, "last_postime": 0 }
                PilotsStatus[row['Pseudo']]=stoelem  
            csvfile.close()

        with open(PILOTS_STATUS, 'w') as out_file:
            json.dump(PilotsStatus, out_file, indent = 4, sort_keys=True)
            out_file.close()      

    else:
        print("%s file not existing" % PILOTS_FILE)


    
    
#     time.sleep(5)
#     stoelem.update({"TakeOff": 1})
#     PilotsStatus[row['Pseudo']]=stoelem
#     with open("pilots.status", 'w') as out_file:
#         json.dump(PilotsStatus, out_file, indent = 4, sort_keys=True)
#     out_file.close()      


# ------------------------------------------------------------------------------
# get info from database
# ------------------------------------------------------------------------------
def fetchDatabase():
    now = int(time.time()-60); # take position from last minute 
    url =FFVL_URL+str(now)
    print("URL=%s" % url)
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
    
    global PilotsStatus
    for elem in infolist:
#         print(elem)
        el = infolist[elem]
        pseudo=el['pseudo']
        if pseudo not in PilotsStatus: 
            # print("%s not in my list" % pseudo)
            continue
        
        pilot = PilotsStatus[pseudo]
        
        # evaluate status of this pilot
        pilot = checkPilot(pilot,el)
        
        PilotsStatus[pseudo] = pilot

        print(el['pseudo'])
        print(el['last_latitude'])
        print(el['last_longitude'])
        print(el['last_altitude'])
    
    # save infos ib backup file
    with open(PILOTS_STATUS, 'w') as out_file:
        json.dump(PilotsStatus, out_file, indent = 4, sort_keys=True)
    out_file.close()      
    

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
    
    tof = 0; lan =0
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

    ps.update({  "last_lat": cur['last_latitude'],\
                 "last_lon": cur['last_longitude'],\
                 "last_alt": cur['last_altitude'],\
                 "last_h_speed": int(last_h_speed),\
                 "last_postime": cur['last_position_utc_timestamp_unix']})
    return(ps)       

# ------------------------------------------------------------------------------
# -----------------------------
#   MAIN PROGRAM
# -----------------------------
# ------------------------------------------------------------------------------
session = HTMLSession()
loadPilotList()
cont = 1

# infolist = fetchDatabase()
# parseData(infolist)

while(cont):
    infolist = fetchDatabase()
    if infolist is None: 
        print("fetch is void")    
    else:
        parseData(infolist)
    print("------------------------------------------------------------")
    time.sleep(REFRESH_PERIOD)







# print(str(hashlib.md5(b'marcel.guwang@free.fr')))
# result = hashlib.md5(m.encode())
# print(result.hexdigest())

