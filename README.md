# tools
Various utilities in python
--------------------------------------------
extractCFD.py : CFD flights extractor

extractCFD.py : parse CFD data base to extract days of flight
extractCFD.py -deco <deco nbr> -an <saeson> [-minkm <min flight dist>] [-minfl <n>]
                   [-out <file>] [-csv] [-html] [-pdf] [ -h ]

Arguments:

  -deco 1: ValLouron 2: St Hilaire 3: St Andre 4: Chalvet  5: Bleine   6: Serpaton
        7: Pouncho   8: Greoliere  9: Arbas   10: Forclaz 11: Planfait

     OR
  -decoId <deco Id>  (as stated in FFVL database)

  -an <year>     : year to explore
  -minkm <km>    : filter flights by distance
  -minfl <n>     : min nbr of flights to consider the day as a good day
  -out <outfile> : output file name/path
  -csv           : generate a csv output file 
  -html          : generate an html output file 
  -pdf           : generate a pdf output file 
  -h             : help

Example:
  I want to filter days with more that 10 flights of 50km at Forclaz for 2022:

  extractCFD.py -deco 10 -an 2022 -minkm 50 -minfl 10 -out Forclaz2022 -csv
