import csv
import re
import json
import urllib
from urllib.request import urlopen
'<--- replaced: import urllib2'
import googlemaps
import datetime
import time
import requests
from math import sqrt
from geopy.distance import great_circle
import os
from os import listdir
from os.path import isfile, join
import sys
import tkinter as tk
'change from: import Tkinter as tk (lower case t)'
from tkinter import filedialog
'change from: import tkFileDialog as filedialog'

# MODE	:	0	:	Traffic and Transit LOS
#			1	:	Traffic LOS only
#			2	:	Transit LOS only
MODE = 0
# Working directory
WORKING_DIR = os.path.dirname(os.path.realpath(__file__)) #Need to edit - My Directory: C:\Users\jdrum\OneDrive\Desktop\Spring 2022\Modeling Hasnine\Discrete Choice\Students Move\SMTO API Input
# Redirect the output
#sys.stdout = open(WORKING_DIR + "\\log.txt", "a")
# Google API key
API_KEY = ''   # CHANGE HERE!
# TTS zones' centroids (lat & long)
ZONES_CENTROIDS_FILE_NAME = WORKING_DIR + '\\Dacentroid.csv'
# Print debug statements
debug = True


'''
	This function finds the first weekday <weekday> next to day <d>
	Monday is 0, and Friday is 4
'''
def next_weekday(d, weekday):
	days_ahead = weekday - d.weekday()
	if days_ahead <= 0: # Target day already happened this week
		days_ahead += 7
	return d + datetime.timedelta(days_ahead)

'''
	This function decodes the polylines returned from Google APIs
	(Downloaded online)
'''
def decode_polyline(polyline_str):
	index, lat, lng = 0, 0, 0
	coordinates = []
	changes = {'latitude': 0, 'longitude': 0}

	# Coordinates have variable length when encoded, so just keep
	# track of whether we've hit the end of the string. In each
	# while loop iteration, a single coordinate is decoded.
	while index < len(polyline_str):
		# Gather lat/lon changes, store them in a dictionary to apply them later
		for unit in ['latitude', 'longitude']:
			shift, result = 0, 0

			while True:
				byte = ord(polyline_str[index]) - 63
				index+=1
				result |= (byte & 0x1f) << shift
				shift += 5
				if not byte >= 0x20:
					break

			if (result & 1):
				changes[unit] = ~(result >> 1)
			else:
				changes[unit] = (result >> 1)

		lat += changes['latitude']
		lng += changes['longitude']

		coordinates.append((lat / 100000.0, lng / 100000.0))

	return coordinates

'''
	Loop over all points of route 1 and check if any of them exists in route 2
	If a point exists on both routes, check if the next point exists in both routes
	If the two points are common between the two routes, calculate the distance between them and add it to the result
'''
def find_overlapping_distance_two_routes(route1, route2):
	route2Index = 0
	result = 0
	for route1Index in range(len(route1)-1):
		try:
			temp = route2[route2Index:].index(route1[route1Index])
			route2Index += temp
		except ValueError:
			continue
		if route2Index == len(route2) - 1:
			break
		if route1[route1Index+1] == route2[route2Index+1]:
			result += great_circle(route1[route1Index], route1[route1Index+1]).meters
			#sqrt((route1[route1Index+1][0]-route1[route1Index][0])**2 + (route1[route1Index+1][1]-route1[route1Index][1])**2)
		route2Index += 1
	return result

'''
	This function returns a list of common distances between routes in the following order:
	(0,1),(0,2),...,(0,n),(1,2),(1,3),...,(1,n),...,(n-1,n)
'''
def find_overlapping_distances_multiple_routes(routes):
	result = []
	for index in range(len(routes)-1):
		for innerIndex in range(index+1,len(routes)):
			result.append(find_overlapping_distance_two_routes(routes[index], routes[innerIndex]))
	return result

'''
	This function returns a list of attributes for two routes (1 untolled + 1 tolled), if exist, in case of 'driving' mode
'''
def find_driving_routes(origin, destination, departureTime, myKey):
	drivingRoutesAttributes = 6
	result = [0 for i in range(drivingRoutesAttributes)]	# in the following format ['Travel time', 'Distance', 'Travel time', 'Distance', 'Tolled Distance', 'Overlapping Distance']

	if origin == destination:
		return result

	serviceUrl = 'https://maps.googleapis.com/maps/api/directions/json?'
	# 'urllib.urlencode was changed to urllib.parse.urlencode()'
	url = serviceUrl + urllib.parse.urlencode((
				('origin', origin),
				('destination', destination),
				('departure_time', departureTime),
				('mode', 'driving'),
				('alternatives', 'true'),
				('key', myKey)
	 ))
	if debug:
		print(url)

	try:
		f = urlopen(url)
		try: js = json.loads(f.read().decode('utf-8'))
		except: js = None
		if 'status' not in js:
			print('==== Failure To Retrieve ====')
			print('Driving from ' + origin + 'to ' + destination)
			print('url: ' + url)
			return result
		elif js['status'] != 'OK':
			print('==== Failure To Retrieve ====')
			print(js['status'])
			print('Driving from ' + origin + 'to ' + destination)
			print('url: ' + url)
			return result
		else:
			foundRoutes = {'untolled':False, 'tolled':False}
			decodedPolylines = [[], []]
			# loop through all available routes
			for routeId in range (0, len(js['routes'])):
				route = js['routes'][routeId]['legs'][0]	# only one trip (one leg)
				if 'duration_in_traffic' in route:
					travelTime = route['duration_in_traffic']['value']	 # in seconds
				else:
					travelTime = route['duration']['value']	 # in seconds
				distance = route['distance']['value']	   # in meters

				tolledDistance = 0
				decodedPolyline = []
				# loop through all steps of this route to check the tolls and get the polyline
				for stepId in range (0, len (route['steps'])):
					step = route['steps'][stepId]
					htmlInstructions = step['html_instructions']
					# check if this step contains driving over a tolled route
					if 'toll road' in htmlInstructions.lower():
						tolledDistance += step['distance']['value']
					encodedPolyline = step['polyline']['points']
					# this is the decoded polyline of the whole route
					decodedPolyline = decodedPolyline + decode_polyline(encodedPolyline)

				# check if this is the first untolled route
				if not foundRoutes['untolled'] and tolledDistance == 0:
					foundRoutes['untolled'] = True
					result[0:2] = [travelTime, distance]
					decodedPolylines[0] = decodedPolyline
				# check if this is the first tolled route
				elif not foundRoutes['tolled'] and tolledDistance != 0:
					foundRoutes['tolled'] = True
					result[2:5] = [travelTime, distance, tolledDistance]
					decodedPolylines[1] = decodedPolyline
				else:
					continue
				# stop looking for more alternative routes, if two routes (tolled & untolled) have already been found
				if foundRoutes['untolled'] and foundRoutes['tolled']:
					break

			# find the overlapping distance if two routes have been found
			if foundRoutes['untolled'] and foundRoutes['tolled']:
				result[5] = find_overlapping_distance_two_routes(decodedPolylines[0], decodedPolylines[1])
	except: return result
	return result

'''
	This function returns a list of attributes for transit routes
'''
def find_transit_routes(origin, destination, departureTime, myKey):
	maxTransitRoutes = 5
	transitRoutesAttributes = 8
	result = [0 for i in range(transitRoutesAttributes * maxTransitRoutes)]

	if origin == destination:
		return result

	''' 
		result is returned in the following format ['Travel time', 'Distance', 'Number of Transfers', 
				'IVTT', 'Access Time', 'Egress Time', 'Walking Distance'] * maxTransitRoutes
				+ ['Overlapping Distance'] * sum(range(maxTransitRoutes)))
	'''
	routeCategories = {'LT':0, 'RT':1, 'LT_RT':2, 'RT_LT':3, 'LT_RT_LT':4}
	serviceUrl = 'https://maps.googleapis.com/maps/api/directions/json?'
	url = serviceUrl + urllib.parse.urlencode((
				('origin', origin),
				('destination', destination),
				('departure_time', departureTime),
				('mode', 'transit'),
				('alternatives', 'true'),
				('key', myKey)
	 ))
	if debug:
		print(url)

	try:
		f = urlopen(url)
		try:
			js = json.loads(f.read().decode('utf-8'))
		except ValueError as err:
			js = None
			print(err)
			return result
		if 'status' not in js:
			print('==== Failure To Retrieve ====')
			print('Transit from ' + origin + 'to ' + destination)
			print('url: ' + url)
			return result
		elif js['status'] != 'OK':
			print('==== Failure To Retrieve ====')
			print(js['status'])
			print('Transit from ' + origin + 'to ' + destination)
			print('url: ' + url)
			return result
		else:
			foundRoutes = {'LT':False, 'RT':False, 'LT_RT':False, 'RT_LT':False, 'LT_RT_LT':False}
			decodedPolylines = [[] for x in range(maxTransitRoutes)]
			# loop through all available routes
			for routeId in range (0, len(js['routes'])):
				route = js['routes'][routeId]['legs'][0]	# only one trip (one leg)

				travelTime = route['duration']['value']	 # in seconds
				distance = route['distance']['value']	   # in meters

				decodedPolyline = []
				walkingDistance = 0
				#walkingDistances = []
				walkingTimes = []
				transitAgencies = []
				numberOfTransfers = -1
				IVTT = 0
				prevStepIsWalking = False
				headway = 0
				# loop through all steps of this route to
				for stepId in range(0, len(route['steps'])):
					step = route['steps'][stepId]
					# if this step is 'walking'
					if step['travel_mode'] == 'WALKING':
						# total walking distance
						walkingDistance += step['distance']['value']
						# list of walking times (consecutive walking steps are added as a single step)
						if prevStepIsWalking:
							walkingTimes[-1] += step['duration']['value']
						else:
							walkingTimes.append(step['duration']['value'])
							prevStepIsWalking = True
						continue
					# if this step is 'transit'
					prevStepIsWalking = False
					numberOfTransfers += 1
					IVTT += step['duration']['value']
					encodedPolyline = step['polyline']['points']
					decodedPolyline = decodedPolyline + decode_polyline(encodedPolyline)
					# check the transit agency name. If 'GO Transit', then it's a regional transit; otherwise, it's a local transit
					if step['transit_details']['line']['agencies'][0]['name'] == 'GO Transit':
						if len(transitAgencies) == 0 or transitAgencies[-1] == 'LT':
							transitAgencies.append('RT')
					else:
						if len(transitAgencies) == 0 or transitAgencies[-1] == 'RT':
							transitAgencies.append('LT')
					#transitLineName = step['transit_details']['line']['name']
					#transitAgency = step['transit_details']['line']['agencies'][0]['name']
					#vehicleType = step['transit_details']['line']['vehicle']['type']
					headway += step['transit_details'].get('headway',0)


				# add this route to the final route set, only if it's the first of its category to be found
				#if len(transitAgencies) != 0 and not foundRoutes['_'.join(transitAgencies)]:
				if len(transitAgencies) != 0 and not foundRoutes.get('_'.join(transitAgencies), True):
					foundRoutes['_'.join(transitAgencies)] = True
					routeCategory = routeCategories['_'.join(transitAgencies)]
					decodedPolylines[routeCategory] = decodedPolyline
					result[routeCategory*transitRoutesAttributes : (routeCategory+1)*transitRoutesAttributes] = \
																 [travelTime, distance, numberOfTransfers, IVTT, walkingTimes[0], walkingTimes[-1], walkingDistance, headway]
	except: return result
	# find the overlapping distances
	result += find_overlapping_distances_multiple_routes(decodedPolylines)
	return result

'''
========================
	script starts here
========================
'''
# Print to the log file
print('===================================================')
print(datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"))

'''# Find (automatically) an input file to process
inputFiles = [f for f in listdir(WORKING_DIR) if(isfile(join(WORKING_DIR, f)) and not f.endswith('_output.csv') and f.startswith('AllModes'))]
if len(inputFiles) == 0:
	sys.exit()
outputFiles = [f for f in listdir(WORKING_DIR) if(isfile(join(WORKING_DIR, f)) and f.endswith('_output.csv'))]
if len(outputFiles) == 0:
	INPUT_FILE_NAME = join(WORKING_DIR, inputFiles[0])
else:
	INPUT_FILE_NAME = None
	for file1 in outputFiles:
		for file2 in inputFiles:
			if not file1.startswith(file2):
				INPUT_FILE_NAME = join(WORKING_DIR, file2)
if INPUT_FILE_NAME is None:
	print 'No more input files are available in this directory'
	print('===================================================')
	sys.exit()	
'''

# Ask the user to choose an input file
root = tk.Tk()
root.withdraw()
# Get the input file name
INPUT_FILE_NAME = filedialog.askopenfilename(initialdir = WORKING_DIR, title = "Select input file", filetypes = (("csv files","*.csv"),("all files","*.*")))
if INPUT_FILE_NAME == '':
	print('No file has been chosen')
	print('===================================================')
	sys.exit()

#INPUT_FILE_NAME = 'D:\\file for Islam\\test.csv'
print('Processing %s' % INPUT_FILE_NAME)

# Output file
OUTPUT_FILE_NAME = INPUT_FILE_NAME + '_output.csv'

# Start calculating execution time
start_time = time.time()

# last two elements in each row
longIndex = -2
latIndex = -1

# maximum routes for each individual
maxTransitRoutes = 5
maxDrivingRoutes = 2

# Labour day: Monday September 3, 2018
baseDateTimeTraffic = datetime.datetime(2022, 4, 27)
baseDateTimeTransit = next_weekday(datetime.datetime.now(), 0)

# reading zones' centroids' coordinates into a dictionary
with open(ZONES_CENTROIDS_FILE_NAME, 'r') as f:
	reader = csv.reader(f)
	myList = list(reader)
	lengthOfList = len(myList[0])
	zonesCentroids = {myList[i][0] : myList[i][1:lengthOfList] for i in range(1, len(myList))}


# read individuals' data
try:
	file = open(INPUT_FILE_NAME, "r")
	line = file.readline()
	line = re.sub('"', '', line)
	line = re.sub('\n', '', line)
	header = re.split(",", line)
	#ODIndex = header.index('O_D')
	originIndex = header.index('OriginZone')
	destinationIndex = header.index('DestinationZone')
	startTimeIndex = header.index('StartTime')
	tripWeekIndex = header.index('trip_week')
	tripWeekdayIndex = header.index('weekday')

	addedHeader = []
	if MODE == 0 or MODE == 1:
		addedHeader += ['Travel time (untolled)', 'Distance (untolled)', 'Travel time (tolled)', 'Distance (tolled)', 'Tolled Distance (tolled)', 'Overlapping Distance (driving)']
	if MODE == 0 or MODE == 2:
		addedHeader += ['Travel time (LT)', 'Distance (LT)', 'Number of Transfers (LT)', 'IVTT (LT)', 'Access Time (LT)', 'Egress Time (LT)', 'Walking Distance (LT)', 'Headway']\
				   + ['Travel time (RT)', 'Distance (RT)', 'Number of Transfers (RT)', 'IVTT (RT)', 'Access Time (RT)', 'Egress Time (RT)', 'Walking Distance (RT)', 'Headway']\
				   + ['Travel time (LT-RT)', 'Distance (LT-RT)', 'Number of Transfers (LT-RT)', 'IVTT (LT-RT)', 'Access Time (LT-RT)', 'Egress Time (LT-RT)', 'Walking Distance (LT-RT)', 'Headway']\
				   + ['Travel time (RT-LT)', 'Distance (RT-LT)', 'Number of Transfers (RT-LT)', 'IVTT (RT-LT)', 'Access Time (RT-LT)', 'Egress Time (RT-LT)', 'Walking Distance (RT-LT)', 'Headway']\
				   + ['Travel time (LT-RT-LT)', 'Distance (LT-RT-LT)', 'Number of Transfers (LT-RT-LT)', 'IVTT (LT-RT-LT)', 'Access Time (LT-RT-LT)', 'Egress Time (LT-RT-LT)', 'Walking Distance (LT-RT-LT)', 'Headway']\
				   + ['Overlapping Distance 1-2', 'Overlapping Distance 1-3', 'Overlapping Distance 1-4', 'Overlapping Distance 1-5'
					  , 'Overlapping Distance 2-3', 'Overlapping Distance 2-4', 'Overlapping Distance 2-5'
					  , 'Overlapping Distance 3-4', 'Overlapping Distance 3-5', 'Overlapping Distance 4-5']

	with open(OUTPUT_FILE_NAME, 'w', newline='') as fp:
		'originally after file name, is was: wb changed to w so the file wasnt byte type '
		a = csv.writer(fp, delimiter=',')
		a.writerow(header + addedHeader)
		individual = 0
		# loop over all the individuals
		while True:
			individual += 1
			line = file.readline()
			line = re.sub('"', '', line)
			line = re.sub('\n', '', line)
			line = re.split(",", line)

			if (line == None) or (len(line) == 1):
				break
			# origin & destination
			try:
				originZone = line[originIndex]
				origin = zonesCentroids[originZone][latIndex] + ',' + zonesCentroids[originZone][longIndex]
				destinationZone = line[destinationIndex]
				destination = zonesCentroids[destinationZone][latIndex] + ',' + zonesCentroids[destinationZone][longIndex]
			except:
				print('cannot find origin and/or destination of individual #%i' %individual)
				continue
			# departure time
			startTime = int(line[startTimeIndex])
			tripWeek = int(line[tripWeekIndex]) - 1
			tripWeekday = int(line[tripWeekdayIndex]) - 1
			if tripWeekday == 9:
				continue
			startDateTimeTraffic = baseDateTimeTraffic + datetime.timedelta(weeks = tripWeek, days = tripWeekday,
											hours = (startTime//100)%24, minutes = startTime%100)
			departureTimeTraffic = googlemaps.convert.time(startDateTimeTraffic)
			startDateTimeTransit = baseDateTimeTransit + datetime.timedelta(weeks = 6, days = tripWeekday,
											hours = (startTime//100)%24, minutes = startTime%100)
			departureTimeTransit = googlemaps.convert.time(startDateTimeTransit)

			# get traffic & transit LOS
			result = line
			if MODE == 0 or MODE == 1:
				result += find_driving_routes(origin, destination, departureTimeTraffic, API_KEY)
			if MODE == 0 or MODE == 2:
				result += find_transit_routes(origin, destination, departureTimeTransit, API_KEY)
			if debug:
				print(result)
			a.writerow(result)

finally:
	file.close()
	print("--- Finished in %s seconds ---" % (time.time() - start_time))
print('===================================================')
