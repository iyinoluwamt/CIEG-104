import datetime
import urllib

import requests
from geopy.distance import great_circle


def next_weekday(d, weekday):
    days_ahead = weekday - d.weekday()
    if days_ahead <= 0:  # Target day already happened this week
        days_ahead += 7
    return d + datetime.timedelta(days_ahead)


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


def find_overlapping_distances_multiple_routes(routes):
    result = []
    for index in range(len(routes) - 1):
        for innerIndex in range(index + 1, len(routes)):
            result.append(find_overlapping_distance_two_routes(routes[index], routes[innerIndex]))
    return result


def find_driving_routes(origin, destination, departure_time, my_key):
    # ['Travel time', 'Distance', 'Travel time', 'Distance', 'Tolled Distance', 'Overlapping Distance']
    driving_routes_attributes = 6
    result = [0 for i in range(driving_routes_attributes)]

    if origin == destination:
        return result

    service_url = 'https://maps.googleapis.com/maps/api/directions/json?'
    url = service_url + urllib.parse.urlencode((
        ('origin', origin),
        ('destination', destination),
        ('departure_time', departure_time),
        ('mode', 'driving'),
        ('alternatives', 'true'),
        ('key', my_key)
    ))

    try:
        r = requests.get(url, timeout=3)
        json = r.json()

        if 'status' not in json:
            print(f'***** Failure to Retrieve *****\nDriving from {origin} to {destination}\nurl: {url}')
            return result
        elif json['status'] != 'OK':
            status = json['status']
            print(f'***** Failure to Retrieve *****\n{status}\nDriving from {origin} to {destination}\nurl: {url}')
            return result

        found_routes = {
            'untolled': False,
            'tolled': False
        }
        decoded_polylines = [[], []]

        routes = json['routes']
        for r_id, route in enumerate(routes):
            route = route['legs'][0]

            if 'duration_in_traffic' in route:
                travel_time = route['duration_in_traffic']['value']  # in seconds
            else:
                travel_time = route['duration']['value']  # in seconds
            distance = route['distance']['value']  # in meters

            tolled_distance = 0
            decoded_polyline = []
            # loop through all steps of this route to check the tolls and get the polyline
            steps = route['steps']
            for s_id, step in enumerate(steps):
                step = route['steps'][s_id]

                html_instructions = step['html_instructions']
                # check if this step contains driving over a tolled route
                if 'toll road' in html_instructions.lower():
                    tolled_distance += step['distance']['value']
                encoded_polyline = step['polyline']['points']
                # this is the decoded polyline of the whole route
                decoded_polyline = decoded_polyline + decode_polyline(encoded_polyline)

                # check if this is the first untolled route
                if not found_routes['untolled'] and tolled_distance == 0:
                    found_routes['untolled'] = True
                    result[0:2] = [travel_time, distance]
                    decoded_polylines[0] = decoded_polyline
                # check if this is the first tolled route
                elif not found_routes['tolled'] and tolled_distance != 0:
                    found_routes['tolled'] = True
                    result[2:5] = [travel_time, distance, tolled_distance]
                    decoded_polylines[1] = decoded_polyline
                else:
                    continue

                # stop looking for more alternative routes, if two routes (tolled & untolled) have already been found
                if found_routes['untolled'] and found_routes['tolled']:
                    break
            # find the overlapping distance if two routes have been found
        if found_routes['untolled'] and found_routes['tolled']:
            result[5] = find_overlapping_distance_two_routes(decoded_polylines[0], decoded_polylines[1])
    except requests.exceptions.HTTPError as errh:
        print("Http Error:", errh)
        return result
    except requests.exceptions.ConnectionError as errc:
        print("Error Connecting:", errc)
        return result
    except requests.exceptions.Timeout as errt:
        print("Timeout Error:", errt)
        return result
    except requests.exceptions.RequestException as err:
        print("OOps: Something Else", err)
        return result

    return result


def find_transit_routes(origin, destination, departure_time, key):
    max_transit_routes = 5
    transit_routes_attributes = 8
    result = [0 for i in range(transit_routes_attributes * max_transit_routes)]

    if origin == destination:
        return result

    ''' 
        result is returned in the following format ['Travel time', 'Distance', 'Number of Transfers', 
                'IVTT', 'Access Time', 'Egress Time', 'Walking Distance'] * max_transit_routes
                + ['Overlapping Distance'] * sum(range(max_transit_routes)))
    '''
    route_categories = {'LT': 0,
                        'RT': 1,
                        'LT_RT': 2,
                        'RT_LT': 3,
                        'LT_RT_LT': 4}
    service_url = 'https://maps.googleapis.com/maps/api/directions/json?'
    url = service_url + urllib.parse.urlencode((
        ('origin', origin),
        ('destination', destination),
        ('departure_time', departure_time),
        ('mode', 'transit'),
        ('alternatives', 'true'),
        ('key', key)
    ))

    try:
        r = requests.get(url)
        json = r.json()

        if 'status' not in json:
            print(f'***** Failure to Retrieve *****\nDriving from {origin} to {destination}\nurl: {url}')
            return result
        elif json['status'] != 'OK':
            status = json['status']
            print(f'***** Failure to Retrieve *****\n{status}\nDriving from {origin} to {destination}\nurl: {url}')
            return result

        found_routes = {'LT': False, 'RT': False, 'LT_RT': False, 'RT_LT': False, 'LT_RT_LT': False}
        decoded_polylines = [[] for x in range(max_transit_routes)]

        # loop through all available routes
        routes = json['routes']
        for r_id, route in enumerate(routes):  # only one trip (one leg)
            route = route['legs'][0]

            travel_time = route['duration']['value']  # in seconds
            distance = route['distance']['value']  # in meters

            decoded_polyline = []
            walking_distance = 0
            walking_times = []
            transit_agencies = []
            number_of_transfers = -1
            IVTT = 0
            prev_step_is_walking = False
            headway = 0

            steps = route['steps']
            for s_id, step in enumerate(steps):
                step = steps[s_id]

                travel_mode = step['travel_mode']
                if travel_mode is 'DRIVING':
                    walking_distance += step['distance']['value']
                    # list of walking times (consecutive walking steps are added as a single step)
                    if prev_step_is_walking:
                        walking_times[-1] += step['duration']['value']
                    else:
                        walking_times.append(step['duration']['value'])
                        prev_step_is_walking = True
                    continue
                prev_step_is_walking = False
                number_of_transfers += 1
                IVTT += step['duration']['value']
                encoded_polyline = step['polyline']['points']
                decoded_polyline = decoded_polyline + decode_polyline(encoded_polyline)

                if ('transit_details' in step) and (
                        step['transit_details']['line']['agencies'][0]['name'] == 'GO Transit'):
                    if len(transit_agencies) == 0 or transit_agencies[-1] == 'LT':
                        transit_agencies.append('RT')
                else:
                    if len(transit_agencies) == 0 or transit_agencies[-1] == 'RT':
                        transit_agencies.append('LT')

                # transitLineName = step['transit_details']['line']['name']
                # transitAgency = step['transit_details']['line']['agencies'][0]['name']
                # vehicleType = step['transit_details']['line']['vehicle']['type']
                if 'transit_details' in step:
                    headway += step['transit_details'].get('headway', 0)

            if len(transit_agencies) != 0 and not found_routes.get('_'.join(transit_agencies), True):
                found_routes['_'.join(transit_agencies)] = True
                route_category = route_categories['_'.join(transit_agencies)]
                decoded_polylines[route_category] = decoded_polyline

                if len(walking_times) != 0:
                    result[route_category * transit_routes_attributes: (route_category + 1) * transit_routes_attributes] = \
                        [travel_time, distance, number_of_transfers, IVTT, walking_times[0], walking_times[-1],
                         walking_distance,
                         headway]
                else:
                    result[route_category * transit_routes_attributes: (route_category + 1) * transit_routes_attributes] = \
                    [travel_time, distance, number_of_transfers, IVTT, 0, 0, walking_distance, headway]

    except requests.exceptions.HTTPError as errh:
        print("Http Error:", errh)
        return result
    except requests.exceptions.ConnectionError as errc:
        print("Error Connecting:", errc)
        return result
    except requests.exceptions.Timeout as errt:
        print("Timeout Error:", errt)
        return result
    except requests.exceptions.RequestException as err:
        print("OOps: Something Else", err)
        return result

    result += find_overlapping_distances_multiple_routes(decoded_polylines)
    return result
