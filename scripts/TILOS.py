import os
import sys
import csv
import json
import re
import time
import datetime
import tkinter as tk
import urllib
from tkinter import filedialog
import googlemaps
import requests
from geopy.distance import great_circle

drive_headers = ['Travel time (untolled)',
                 'Distance (untolled)',
                 'Travel time (tolled)',
                 'Distance (tolled)',
                 'Tolled Distance (tolled)',
                 'Overlapping Distance (driving)']
transit_headers = ['Travel time (LT)', 'Distance (LT)', 'Number of Transfers (LT)', 'IVTT (LT)',
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


class TILOS:
    def __init__(self, config_path='../util/config.json', zone_centroid_path='../data/Dacentroid.csv', output_path="../data/test_output.csv", mode=2):
        self.key = json.load(open(config_path))['apiKey']
        self.zones_centroids = self.load_zones_centroids(zone_centroid_path)

        self.base_datetime_traffic = datetime.datetime.now()
        self.base_datetime_transit = datetime.datetime.now()

        self.mode = mode
        self.output_path = output_path

        # last two elements in each row
        self.long_index = -2
        self.lat_index = -1

        # maximum routes for each individual
        self.max_transit_routes = 5
        self.max_driving_routes = 2

    @staticmethod
    def load_zones_centroids(path):
        with open(path, 'r') as f:
            reader = csv.reader(f)
            centroids = list(reader)
            return {centroids[i][0]: centroids[i][1:len(centroids[0])] for i in range(1, len(centroids))}

    @staticmethod
    def get_input_file_name():
        root = tk.Tk()
        root.withdraw()
        working_dir = os.path.dirname(os.path.realpath(__file__))
        input_file_name = filedialog.askopenfilename(
            initialdir=working_dir,
            title="Select input file",
            filetypes=(
                ("csv files", "*.csv"),
                ("all files", "*.*")
            )
        )
        if input_file_name == '':
            print('No file has been chosen')
            print('*' * 50)
            sys.exit()
        return input_file_name

    @staticmethod
    def next_weekday(d, weekday):
        days_ahead = weekday - d.weekday()
        if days_ahead <= 0:  # Target day already happened this week
            days_ahead += 7
        return d + datetime.timedelta(days_ahead)

    def build_url(self, origin, destination, departure_time, mode):
        service_url = 'https://maps.googleapis.com/maps/api/directions/json?'
        url = service_url + urllib.parse.urlencode((
            ('origin', origin),
            ('destination', destination),
            ('departure_time', departure_time),
            ('mode', mode),
            ('alternatives', 'true'),
            ('key', self.key)
        ))
        return url

    @staticmethod
    def request_route_data(url):
        try:
            r = requests.get(url, timeout=3)
            return r.json()
        except requests.exceptions.HTTPError as errh:
            print("Http Error:", errh)
        except requests.exceptions.ConnectionError as errc:
            print("Error Connecting:", errc)
        except requests.exceptions.Timeout as errt:
            print("Timeout Error:", errt)
        except requests.exceptions.RequestException as err:
            print("OOps: Something Else", err)
        return None

    @staticmethod
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
                    index += 1
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

    @staticmethod
    def find_overlapping_distance_two_routes(route1, route2):
        route2Index = 0
        result = 0
        for route1Index in range(len(route1) - 1):
            try:
                temp = route2[route2Index:].index(route1[route1Index])
                route2Index += temp
            except ValueError:
                continue
            if route2Index == len(route2) - 1:
                break
            if route1[route1Index + 1] == route2[route2Index + 1]:
                result += great_circle(route1[route1Index], route1[route1Index + 1]).meters
            # sqrt((route1[route1Index+1][0]-route1[route1Index][0])**2 + (route1[route1Index+1][1]-route1[route1Index][1])**2)
            route2Index += 1
        return result

    def find_overlapping_distances_multiple_routes(self, routes):
        result = []
        for index in range(len(routes) - 1):
            for innerIndex in range(index + 1, len(routes)):
                result.append(self.find_overlapping_distance_two_routes(routes[index], routes[innerIndex]))
        return result

    @staticmethod
    def handle_walking_step(step, prev_step_is_walking, walking_times):
        walking_distance = step['distance']['value']
        if prev_step_is_walking:
            walking_times[-1] += step['duration']['value']
        else:
            walking_times.append(step['duration']['value'])
            prev_step_is_walking = True
        return walking_distance, prev_step_is_walking

    def handle_transit_step(self, step, transit_agencies):
        number_of_transfers = 1
        IVTT = step['duration']['value']
        decoded_polyline = self.decode_polyline(step['polyline']['points'])

        if ('transit_details' in step) and (step['transit_details']['line']['agencies'][0]['name'] == 'GO Transit'):
            if len(transit_agencies) == 0 or transit_agencies[-1] == 'LT':
                transit_agencies.append('RT')
        else:
            if len(transit_agencies) == 0 or transit_agencies[-1] == 'RT':
                transit_agencies.append('LT')

        headway = step['transit_details'].get('headway', 0) if 'transit_details' in step else 0

        return number_of_transfers, IVTT, decoded_polyline, headway

    def process_route_steps(self, steps):
        walking_distance = 0
        walking_times = []
        transit_agencies = []
        number_of_transfers = -1
        IVTT = 0
        prev_step_is_walking = False
        headway = 0
        decoded_polyline = []

        for step in steps:
            travel_mode = step['travel_mode']
            if travel_mode == 'WALKING':
                walk_dist, prev_step_is_walking = self.handle_walking_step(step, prev_step_is_walking, walking_times)
                walking_distance += walk_dist
            else:
                prev_step_is_walking = False
                transfers, ivtt, poly, hw = self.handle_transit_step(step, transit_agencies)
                number_of_transfers += transfers
                IVTT += ivtt
                decoded_polyline += poly
                headway += hw

        return walking_distance, walking_times, transit_agencies, number_of_transfers, IVTT, headway, decoded_polyline

    @staticmethod
    def update_route_results(result, route_category, travel_time, distance, number_of_transfers, IVTT,
                             walking_times, walking_distance, headway, transit_routes_attributes):
        start_index = route_category * transit_routes_attributes
        end_index = (route_category + 1) * transit_routes_attributes
        if walking_times:
            result[start_index:end_index] = [travel_time, distance, number_of_transfers, IVTT, walking_times[0],
                                             walking_times[-1], walking_distance, headway]
        else:
            result[start_index:end_index] = [travel_time, distance, number_of_transfers, IVTT, 0, 0, walking_distance,
                                             headway]

    def find_transit_routes(self, origin, destination, departure_time):
        max_transit_routes = 5
        transit_routes_attributes = 8
        result = [0] * (transit_routes_attributes * max_transit_routes)

        if origin == destination:  # If origin and destination are the same, return an empty result
            return result

        # Define route categories and their indices in the result list
        route_categories = {'LT': 0, 'RT': 1, 'LT_RT': 2, 'RT_LT': 3, 'LT_RT_LT': 4}

        # Build the URL for the API request
        url = self.build_url(origin, destination, departure_time, 'transit')

        try:
            print(f"✅ REQUEST: {url}")
            json = self.request_route_data(url)

            # Check for a valid response
            if json is None or 'status' not in json:
                print(f'***** Failure to Retrieve *****\nDriving from {origin} to {destination}\nurl: {url}')
                return result
            elif json['status'] != 'OK':
                status = json['status']
                print(f'***** Failure to Retrieve *****\n{status}\nDriving from {origin} to {destination}\nurl: {url}')
                return result

            # Initialize variables to track found routes and decoded polylines
            found_routes = {'LT': False, 'RT': False, 'LT_RT': False, 'RT_LT': False, 'LT_RT_LT': False}
            decoded_polylines = [[] for x in range(max_transit_routes)]

            # Loop through all available routes
            routes = json['routes']
            for r_id, route in enumerate(routes):
                route = route['legs'][0]
                travel_time = route['duration']['value']  # in seconds
                distance = route['distance']['value']  # in meters

                steps = route['steps']
                (walking_distance, walking_times, transit_agencies, number_of_transfers,
                 IVTT, headway, decoded_polyline) = self.process_route_steps(steps)

                # If the current route hasn't been found yet, update the result and found_routes
                if len(transit_agencies) != 0 and not found_routes.get('_'.join(transit_agencies), True):
                    found_routes['_'.join(transit_agencies)] = True
                    route_category = route_categories['_'.join(transit_agencies)]
                    decoded_polylines[route_category] = decoded_polyline

                    self.update_route_results(result, route_category, travel_time, distance, number_of_transfers, IVTT,
                                              walking_times, walking_distance, headway, transit_routes_attributes)

        except Exception as err:
            print("Error:", err)
            return result

        result += self.find_overlapping_distances_multiple_routes(decoded_polylines)
        return result

    def process_driving_routes(self, json, origin, destination, url):
        if json.get('status') != 'OK':
            print(f'***** Failure to Retrieve *****\nDriving from {origin} to {destination}\nurl: {url}')
            return None

        result = [0] * 6
        found_routes = {'untolled': False, 'tolled': False}
        decoded_polylines = [[], []]

        for route in json['routes']:
            leg = route['legs'][0]
            travel_time = leg.get('duration_in_traffic', leg['duration'])['value']
            distance = leg['distance']['value']

            tolled_distance = sum(
                step['distance']['value'] for step in leg['steps'] if 'toll road' in step['html_instructions'].lower())

            decoded_polyline = [coord for step in leg['steps'] for coord in
                                self.decode_polyline(step['polyline']['points'])]

            if not found_routes['untolled'] and tolled_distance == 0:
                found_routes['untolled'] = True
                result[0:2] = [travel_time, distance]
                decoded_polylines[0] = decoded_polyline
            elif not found_routes['tolled'] and tolled_distance != 0:
                found_routes['tolled'] = True
                result[2:5] = [travel_time, distance, tolled_distance]
                decoded_polylines[1] = decoded_polyline

            if found_routes['untolled'] and found_routes['tolled']:
                result[5] = self.find_overlapping_distance_two_routes(decoded_polylines[0], decoded_polylines[1])
                break

        return result

    def find_driving_routes(self, origin, destination, departure_time):
        # ['Travel time', 'Distance', 'Travel time', 'Distance', 'Tolled Distance', 'Overlapping Distance']
        driving_routes_attributes = 6
        result = [0 for i in range(driving_routes_attributes)]

        if origin == destination:
            return result

        url = self.build_url(origin, destination, departure_time, 'driving')
        print(f"✅ REQUEST: {url}")

        json = self.request_route_data(url)

        if json is None:
            return result

        routes = self.process_driving_routes(json, origin, destination, url)
        if routes is None:
            return result

        # Process routes (existing code)
        return result

    def remove_chars(self, text):
        pattern = re.compile(r'["\n]')
        return pattern.sub('', text)

    def get_header(self, file):
        header = self.remove_chars(file.readline()).split(",")
        origin_index, destination_index, start_time_index = header.index('OriginZone'), header.index(
            'DestinationZone'), header.index('StartTime')
        trip_week_index, trip_weekday_index = header.index('trip_week'), header.index('weekday')

        added_header = []
        if self.mode in (0, 1):
            added_header += drive_headers
        if self.mode in (0, 2):
            added_header += transit_headers

        return header, added_header, origin_index, destination_index, start_time_index, trip_week_index, trip_weekday_index

    def process_individual(self, individual, line, origin_index, destination_index, start_time_index, trip_week_index,
                           trip_weekday_index):
        try:
            origin_zone, destination_zone = line[origin_index], line[destination_index]
            origin = ','.join(self.zones_centroids[origin_zone][i] for i in (self.lat_index, self.long_index))
            destination = ','.join(self.zones_centroids[destination_zone][i] for i in (self.lat_index, self.long_index))
        except:
            print(f'cannot find origin and/or destination of individual #{individual}')
            return None

        start_time, trip_week, trip_weekday = int(line[start_time_index]), int(line[trip_week_index]) - 1, int(
            line[trip_weekday_index]) - 1
        if trip_weekday == 9:
            return None

        start_date_time_traffic = self.base_datetime_traffic + datetime.timedelta(weeks=trip_week, days=trip_weekday,
                                                                                  hours=(start_time // 100) % 24,
                                                                                  minutes=start_time % 100)
        departure_time_traffic = googlemaps.convert.time(start_date_time_traffic)
        start_date_time_transit = self.base_datetime_transit + datetime.timedelta(weeks=6, days=trip_weekday,
                                                                                  hours=(start_time // 100) % 24,
                                                                                  minutes=start_time % 100)
        departure_time_transit = googlemaps.convert.time(start_date_time_transit)

        result = line
        if self.mode in (0, 1):
            result += self.find_driving_routes(origin, destination, departure_time_traffic)
        if self.mode in (0, 2):
            result += self.find_transit_routes(origin, destination, departure_time_transit)

        return result

    def process_input_file(self, input_file_name):
        start_time = time.time()

        with open(input_file_name, "r") as file, open(self.output_path, 'w', newline='') as output:
            a = csv.writer(output, delimiter=',')
            header, added_header, origin_index, destination_index, start_time_index, trip_week_index, trip_weekday_index = self.get_header(
                file)
            a.writerow(header + added_header)

            for individual, line in enumerate(file, start=1):
                line = self.remove_chars(line).split(",")
                if not line or len(line) == 1:
                    break

                result = self.process_individual(individual, line, origin_index, destination_index, start_time_index,
                                                 trip_week_index, trip_weekday_index)
                if result is not None:
                    print(f"⏺️ RECV: {result}")
                    a.writerow(result)

        print(f"☑️ Finished in {round(time.time() - start_time, 2)} seconds")

    def run(self):
        input_file_name = self.get_input_file_name()
        self.process_input_file(input_file_name)


if __name__ == '__main__':
    tilos = TILOS(mode=0)
    tilos.run()
