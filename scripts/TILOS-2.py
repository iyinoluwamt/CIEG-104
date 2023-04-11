import csv
import datetime
import json
import os
import re
import sys
import time
from tkinter import filedialog

import googlemaps
import tkinter as tk
from directional import next_weekday, find_driving_routes, find_transit_routes

CONFIG = json.load(open('../util/config.json'))
ZONE_CENTROID_PATH = '../data/Dacentroid.csv'

root = tk.Tk()
root.withdraw()
# Get the input file name
WORKING_DIR = os.path.dirname(os.path.realpath(__file__))
INPUT_FILE_NAME = filedialog.askopenfilename(
	initialdir=WORKING_DIR,
	title="Select input file",
	filetypes=(
		("csv files", "*.csv"),
		("all files", "*.*")
	)
)
if INPUT_FILE_NAME == '':
	print('No file has been chosen')
	print('*' * 50)
	sys.exit()

ZONES_CENTROIDS_FILE_NAME = '../data/Dacentroid.csv'
with open(ZONES_CENTROIDS_FILE_NAME, 'r') as f:
	reader = csv.reader(f)
	centroids = list(reader)
	zones_centroids = {centroids[i][0]: centroids[i][1:len(centroids[0])] for i in range(1, len(centroids))}

MODE = 2

# last two elements in each row
long_index = -2
lat_index = -1

# maximum routes for each individual
max_transit_routes = 5
max_driving_routes = 2

base_datetime_traffic = datetime.datetime.now()
base_datetime_transit = next_weekday(datetime.datetime.now(), 0)

start_time = time.time()
try:
	file = open(INPUT_FILE_NAME, "r")
	line = file.readline()
	line = re.sub('"', '', line)
	line = re.sub('\n', '', line)
	header = re.split(",", line)

	# ODIndex = header.index('O_D')
	origin_index = header.index('OriginZone')
	destination_index = header.index('DestinationZone')
	start_time_index = header.index('StartTime')
	trip_week_index = header.index('trip_week')
	trip_weekday_index = header.index('weekday')

	added_header = []
	if MODE == 0 or MODE == 1:
		added_header += ['Travel time (untolled)',
						 'Distance (untolled)',
						 'Travel time (tolled)',
						 'Distance (tolled)',
						 'Tolled Distance (tolled)',
						 'Overlapping Distance (driving)']
	if MODE == 0 or MODE == 2:
		added_header += ['Travel time (LT)', 'Distance (LT)', 'Number of Transfers (LT)', 'IVTT (LT)',
						 'Access Time (LT)', 'Egress Time (LT)', 'Walking Distance (LT)', 'Headway'] \
						+ ['Travel time (RT)', 'Distance (RT)', 'Number of Transfers (RT)', 'IVTT (RT)',
						   'Access Time (RT)', 'Egress Time (RT)', 'Walking Distance (RT)', 'Headway'] \
						+ ['Travel time (LT-RT)', 'Distance (LT-RT)', 'Number of Transfers (LT-RT)', 'IVTT (LT-RT)',
						   'Access Time (LT-RT)', 'Egress Time (LT-RT)', 'Walking Distance (LT-RT)', 'Headway'] \
						+ ['Travel time (RT-LT)', 'Distance (RT-LT)', 'Number of Transfers (RT-LT)', 'IVTT (RT-LT)',
						   'Access Time (RT-LT)', 'Egress Time (RT-LT)', 'Walking Distance (RT-LT)', 'Headway'] \
						+ ['Travel time (LT-RT-LT)', 'Distance (LT-RT-LT)', 'Number of Transfers (LT-RT-LT)',
						   'IVTT (LT-RT-LT)', 'Access Time (LT-RT-LT)', 'Egress Time (LT-RT-LT)',
						   'Walking Distance (LT-RT-LT)', 'Headway'] \
						+ ['Overlapping Distance 1-2', 'Overlapping Distance 1-3', 'Overlapping Distance 1-4',
						   'Overlapping Distance 1-5'
							, 'Overlapping Distance 2-3', 'Overlapping Distance 2-4', 'Overlapping Distance 2-5'
							, 'Overlapping Distance 3-4', 'Overlapping Distance 3-5', 'Overlapping Distance 4-5']

	OUTPUT_FILE_NAME = '../data/test_output.csv'
	with open(OUTPUT_FILE_NAME, 'w', newline='') as output:
		a = csv.writer(output, delimiter=',')
		a.writerow(header + added_header)
		individual = 0
		# loop over all the individuals

		while True:
			individual += 1
			line = file.readline()
			line = re.sub('"', '', line)
			line = re.sub('\n', '', line)
			line = re.split(",", line)
			if (line is None) or (len(line) == 1):
				break

			try:
				origin_zone = line[origin_index]
				origin = zones_centroids[origin_zone][lat_index] + ',' + zones_centroids[origin_zone][long_index]
				destination_zone = line[destination_index]
				destination = zones_centroids[destination_zone][lat_index] + ',' + zones_centroids[destination_zone][long_index]
			except:
				print('cannot find origin and/or destination of individual #%i' %individual)
				continue

			startTime = int(line[start_time_index])
			tripWeek = int(line[trip_week_index]) - 1
			tripWeekday = int(line[trip_weekday_index]) - 1

			if tripWeekday == 9:
				continue
			start_date_time_traffic = base_datetime_traffic + datetime.timedelta(weeks=tripWeek, days=tripWeekday,
																			hours=(startTime // 100) % 24,
																			minutes=startTime % 100)
			departure_time_traffic = googlemaps.convert.time(start_date_time_traffic)
			startDateTimeTransit = base_datetime_transit + datetime.timedelta(weeks=6, days=tripWeekday,
																			hours=(startTime // 100) % 24,
																			minutes=startTime % 100)
			departureTimeTransit = googlemaps.convert.time(startDateTimeTransit)

			# get traffic & transit LOS
			result = line
			if MODE == 0 or MODE == 1:
				result += find_driving_routes(origin, destination, departure_time_traffic, CONFIG['apiKey'])
			if MODE == 0 or MODE == 2:
				result += find_transit_routes(origin, destination, departureTimeTransit, CONFIG['apiKey'])
			print(result)
			a.writerow(result)

finally:
	file.close()
	print(f"***** Finished in {time.time() - start_time} seconds *****")
