#!/usr/bin/python3

# ------------------------------------------------------------------------------
# 
# script to extract best flight days from FFVL CFD web site for a given site
#   and correlate with weather conditions
#   report in a csv/html/pdf file
# 
# 
# Author: Pascal Caunegre
# Licence: CC-BY-NC-SA
# ------------------------------------------------------------------------------

# For PDF file generation, it may be needed to install xhtml2pdf lib:
# pip3 install xhtml2pdf


import sys
import os
import time
import re
from requests_html import HTMLSession
import xml.etree.ElementTree as ET
import csv


# TOUS LES VOLS:
# -------------------------------------
# https://parapente.ffvl.fr/cfd/liste

# TOUS LES VOLS DEPUIS UN SITE:
# -------------------------------------
# https://parapente.ffvl.fr/cfd/liste/deco/20356422

# TOUS LES VOLS DEPUIS UN SITE A UNE DATE:      ?sort=asc&order=date
# -------------------------------------
#  https://parapente.ffvl.fr/cfd/liste/saison/2019/deco/20356422/date/2020-07-13
#  https://parapente.ffvl.fr/cfd/liste/saison/<SAISON>/deco/<DECO>/date/<YYYY-MM-DD>
#  Decos:
#  St Hilaire : 20356422
#  Serpaton   : 20356466
#  Pouncho    : 20356645
#  Arbas      : 20356144
#  Greoliere  : 20356469
#  Bleine     : 20331480
#  St Andre   : 20283954
#  Chalvet W  : 20338965
#  ValLouron  : 20334047
#  Forclaz    : 20332479
#  Planfait   : 20358047

DECOLIST  = [0, 20334047, 20356422, 20283954, 20338965, 20331480, 20356466, 20356645, 20356469, 20356144, 20332479, 20358047 ]
DECONAMES = [0, 'ValLouron', 'St Hilaire', 'St Andre', 'Chalvet W', 'Bleine', 'Serpaton', 'Pouncho', 'Greoliere', 'Arbas', 'Forclaz', 'Planfait' ]


# Zunino:   https://parapente.ffvl.fr/pilote/20828/2023
# moi:      https://parapente.ffvl.fr/pilote/2524/2023
# Hz        https://parapente.ffvl.fr/pilote/17064/2023


SOURCE_URL="https://parapente.ffvl.fr/cfd/liste/saison/"
WTHRMAP_URL="https://www.wetterzentrale.de/reanalysis.php?"

#https://meteocentre.com/radiosonde/get_sounding.php?lang=fr&show=1&hist=1&yyyy=2024&mm=04&dd=27&area=qc&stn=07510&run=12
# https://meteocentre.com/radiosonde/get_sounding.php?lang=fr&yyyy=2024&mm=04&dd=27&area=qc&stn=07510&run=12
# stn=0714 : Trappes
# stn=07510 : Bordeaux
SOUNDMAP_URL="https://meteocentre.com/radiosonde/get_sounding.php?lang=fr&show=1&hist=1"
SOUNDINGSTATION = '07510'

# ------------------------------------------------------------------------------
# help
# ------------------------------------------------------------------------------
def userHelp():
    print("%s : parse CFD data base to extract days of flight" % sys.argv[0] )
    print("%s -deco <deco nbr> -an <saeson> [-minkm <min flight dist>] [-minfl <n>]\n\
                   [-out <file>] [-csv] [-html] [-pdf] [ -h ]" % sys.argv[0] )
    print("\nArguments:\n" )
    print("  -deco 1: ValLouron 2: St Hilaire 3: St Andre 4: Chalvet  5: Bleine   6: Serpaton" )
    print("        7: Pouncho   8: Greoliere  9: Arbas   10: Forclaz 11: Planfait\n" )
    print("     OR\n  -decoId <deco Id>  (as stated in FFVL database)\n" )
    print("  -an <year>     : year to explore" )
    print("  -minkm <km>    : filter flights by distance" )
    print("  -minfl <n>     : min nbr of flights to consider the day as a good day" )
    print("  -out <outfile> : output file name/path" )
    print("  -csv           : generate a csv output file " )
    print("  -html          : generate an html output file " )
    print("  -pdf           : generate a pdf output file " )
    print("  -h             : help" )
    print("" )
    print("Example:" )
    print("  I want to filter days with more that 5 flights of 40km at Forclaz for 2022" )
    print("%s -deco 10 -an 2022 -minkm 40 -minfl 5 -out Forclaz2022 -csv\n" % sys.argv[0] )
    exit(0)

# ------------------------------------------------------------------------------
# parse args
# ------------------------------------------------------------------------------
def readArgs():
    
    global deco, deconame, season, minkm, minfl, outfile, csv, html, pdf
    
    n=len(sys.argv)
    if (n<5):
        userHelp()
        
    i=1; minkm=30; minfl=1 ; outfile="result.csv"; csv = 0; html = 0; pdf = 0; 
    while(i<n):
        if sys.argv[i]=="-deco":
            deco     = DECOLIST[int(sys.argv[i+1])]
            deconame = DECONAMES[int(sys.argv[i+1])]
            i=i+1
        elif sys.argv[i]=="-decoId": 
            deco = sys.argv[i+1]
            deconame = deco
            i=i+1
        elif sys.argv[i]=="-an": 
            season = int(sys.argv[i+1])
            i=i+1
        elif sys.argv[i]=="-minkm": 
            minkm = sys.argv[i+1]
            i=i+1
        elif sys.argv[i]=="-minfl": 
            minfl = int(sys.argv[i+1])
            i=i+1
        elif sys.argv[i]=="-out": 
            outfile = sys.argv[i+1]
            i=i+1
        elif sys.argv[i]=="-csv": 
            csv = 1
        elif sys.argv[i]=="-html": 
            html = 1
        elif sys.argv[i]=="-pdf": 
            pdf = 1
        elif sys.argv[i]=="-h": 
            userHelp()
        else: 
            print("Incorrect argument(s) !!!")
            userHelp()
        i+=1



# ------------------------------------------------------------------------------
# get flights data in xml format
# https://parapente.ffvl.fr/cfd/liste/saison/2023/deco/20356422?xml=1
# ------------------------------------------------------------------------------
def getCFDat(year,site):

    global SOURCE_URL

    # forge url to get data
    URL = SOURCE_URL + str(year) + "/deco/" + str(site) + "?xml=1"
    print("Exploring %s" % URL)
    
    # get html data
    ret = session.get(URL)
    htmlContent = ret.content.decode('utf-8')

    return(htmlContent)


# ------------------------------------------------------------------------------
# parse flights data 
# 
# ------------------------------------------------------------------------------
def getAndSortData(year):
    
    global dateTab
    htmlContent = getCFDat(year,deco)
    tree = ET.fromstring(htmlContent)
    # sort data
    # -----------------------------
    nbrLine = len(tree[0][0])
    pattern = str(season)
    pattern += '.*'
    for i in range(nbrLine-1):
        elem = tree[0][0][i]
        elemDict = elem.attrib
        # print(elemDict.keys())
        date = elemDict['date']
        if re.match(pattern,date):
            if (float(elemDict['distance']) >= int(minkm)):
                if date in dateTab:
                    dateTab[date] = dateTab[date] + 1
                else:
                    dateTab[date] = 1


# ------------------------------------------------------------------------------
# generate a csv formatted ouput, report in csv file 
# 
# https://www.wetterzentrale.de/reanalysis.php?jaar=2023&maand=4&dag=7&uur=000&var=1&map=1&model=avn
# ------------------------------------------------------------------------------
def csvOutput():
    
    global dateTab
    
    # forge output
    # -----------------------------
    headerlist = [ deconame, str(season), '' ]
    outStr = ",".join(headerlist) + '\n'
    headerlist = [ 'Date', 'NbVols > '+minkm+'km' , 'Cartes Meteo'  ]
    outStr += ",".join(headerlist) + '\n'

    for d in sorted(dateTab.keys()):
        if (dateTab[d] >= minfl):
            spl_date = d.split('-')
            wthrmap1 = forgeLink(spl_date,'1')
            wthrmap2 = forgeLink(spl_date,'2')
            soundmap = forgeSdLink(spl_date,SOUNDINGSTATION)
            lineList = [ d, str(dateTab[d]), wthrmap1, wthrmap2, soundmap ]
            outStr += ",".join(lineList) + '\n'
    
    # output in csv file
    # -----------------------------
    f = open(outfile+'.csv', 'w', newline='')
    print(outStr, file=f)
    f.close 
    print("CSV file generated") 

    return(outStr)

# ------------------------------------------------------------------------------
# utilities to forge links
# ------------------------------------------------------------------------------
def forgeLink(spl_date,var):

    ret = WTHRMAP_URL + 'jaar=' + spl_date[0] +'&maand=' + spl_date[1] + '&dag=' + spl_date[2] + '&uur=000&var='+var+'&map=1&model=avn'
    return(ret)
    
def forgeSdLink(spl_date,station):

    ret = SOUNDMAP_URL + '?lang=fr&yyyy=' + spl_date[0] + '&mm=' + spl_date[1] + '&dd=' + spl_date[2] + '&area=qc&stn=' + station + '&run=12'
    return(ret)


# ------------------------------------------------------------------------------
# generate a html formatted ouput
# 
# https://parapente.ffvl.fr/cfd/liste/saison/<SAISON>/deco/<DECO>/date/<YYYY-MM-DD>
# ------------------------------------------------------------------------------
def htmlOutput():

    global dateTab
    outStr = '<table border="1" class="dataframe">\n'
    outStr += '<thead><tr><th>' + deconame + '</th><th>' + str(season) + '</th></tr></thead>\n'
    outStr += '<tbody>\n'
    outStr += '<tr><th>Date</th><th>NbVols > ' + minkm + 'km</th><th>Cartes Meteo</th><th>Vols</th></tr>\n'
    FL_URL="https://parapente.ffvl.fr/cfd/liste/saison/"
    
    for d in sorted(dateTab.keys()):
        if (dateTab[d] >= minfl):
            spl_date = d.split('-')
            wthrmap1 = forgeLink(spl_date,'1')
            wthrmap2 = forgeLink(spl_date,'2')
            soundmap = forgeSdLink(spl_date,SOUNDINGSTATION)
            yr = season
            if (int(spl_date[1]) < 8):
                yr -= 1
            fl_link = FL_URL + str(yr) + '/deco/' + str(deco) + '/date/' + d + '?sort=desc&order=km'
            
            outStr += '<tr><th>'+str(d)+'</th><th>'+str(dateTab[d])+'</th><th><a href="'+\
                wthrmap1+'">Pression</a>  |  <a href="'+wthrmap2+'">Z850</a>   |  <a href="'+soundmap+'">Sounding</a> </th><th><a href="'+fl_link+'">Traces CFD</a></th></tr>\n'
    
    outStr += '</tbody>\n'
    outStr += '</table>\n'
    
    return(outStr)

    

# ------------------------------------------------------------------------------
# -----------------------------
#   MAIN PROGRAM
# -----------------------------
# ------------------------------------------------------------------------------
readArgs()

# get data
# -----------------------------
session = HTMLSession()
dateTab={}
# we need to parse 2 CFD seasons to gather a civil year
getAndSortData(season-1)
getAndSortData(season)

if csv:
    csvOutput()


if (html or pdf):
    html_content=htmlOutput()
    if html:
        f = open(outfile+'.html', 'w', newline='')
        print(html_content, file=f)
        f.close
        print("HTML file generated") 
    
    if pdf:
        pdf_file = outfile + '.pdf'
        try:
            from xhtml2pdf import pisa
        except ModuleNotFoundError:
            print("You need to install an extra lib with: pip3 install xhtml2pdf")
            exit(0)
            
        # Generate PDF
        with open(pdf_file, "wb") as f:
            pisa_status = pisa.CreatePDF(html_content, dest=f)
            print("PDF file generated") 

         
# ------------------------------------------------------------------------------
# ------------------------------------------------------------------------------
# ------------------------------------------------------------------------------
    
