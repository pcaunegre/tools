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

FFVL_URL="https://data.ffvl.fr/api/?mode=json&key=79ef8d9f57c10b394b8471deed5b25e7&ffvl_tracker_key=all&from_utc_timestamp="
REFRESH_PERIOD = 60
PILOTS_FILE = "pilots.csv"

# ------------------------------------------------------------------------------
# load pilot list from input csv file
# preset the table PilotsStatus and stores in a backup file
# initial storage of that table in a backup file (json format)
# ------------------------------------------------------------------------------
def loadPilotList():
    global PilotsStatus

    PilotsStatus = {}
    with open(PILOTS_FILE, newline='') as csvfile:
        reader = csv.DictReader(csvfile)
        for row in list(reader):
            print(row['Nom'])
            stoelem = { "Name": row['Prenom'], "Surname": row['Nom'], "TakeOff": 0, "Landed": 0, "Standing": 0, "Cleared": 0, "last_lat": 0,"last_lon": 0, "last_alt": 0, "last_postime": 0 }
            PilotsStatus[row['Pseudo']]=stoelem  
    
    with open("pilots.status", 'w') as out_file:
        json.dump(PilotsStatus, out_file, indent = 4, sort_keys=True)
    out_file.close()      
    
    
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
    ret = session.get(url)
    htmlContent = ret.content.decode('utf-8')
    l = json.loads(htmlContent)
    return(l)


# ------------------------------------------------------------------------------
# parse data from database
# update status for each pilot
# ------------------------------------------------------------------------------
def parseData(infolist):
    
    global PilotsStatus
    for elem in infolist:
        print(elem)
        el = infolist[elem]
        pseudo=el['pseudo']
        if pseudo not in PilotsStatus: 
            print("%s not in my list" % pseudo)
            continue
        pilot = PilotsStatus[pseudo]
        pilot.update({  "last_lat": el['last_latitude'],\
                        "last_lon": el['last_longitude'],\
                        "last_alt": el['last_altitude'],\
                        "last_postime": el['last_position_utc_timestamp_unix']})
        PilotsStatus[pseudo] = pilot

        print(el['pseudo'])
        print(el['last_latitude'])
        print(el['last_longitude'])
        print(el['last_altitude'])
    
    # save infos ib backup file
    with open("pilots.status", 'w') as out_file:
        json.dump(PilotsStatus, out_file, indent = 4, sort_keys=True)
    out_file.close()      
    


# ------------------------------------------------------------------------------
# -----------------------------
#   MAIN PROGRAM
# -----------------------------
# ------------------------------------------------------------------------------
session = HTMLSession()
loadPilotList()
cont = 1

infolist = fetchDatabase()
parseData(infolist)

# while(cont):
#     infolist = fetchDatabase()
#     parseData(infolist)
#     
#     time.sleep(REFRESH_PERIOD)







# print(str(hashlib.md5(b'marcel.guwang@free.fr')))
# result = hashlib.md5(m.encode())
# print(result.hexdigest())

