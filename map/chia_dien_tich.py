import math
import sys
import copy
import os
from scipy.spatial import ConvexHull
import numpy as np

MAP_DIR = os.path.dirname(os.path.abspath(__file__))
BASE_DIR = os.path.dirname(MAP_DIR)
MISSION_DIR = os.path.join(BASE_DIR, "mission")


def mission_file_path(filename):
    os.makedirs(MISSION_DIR, exist_ok=True)
    return os.path.join(MISSION_DIR, filename)



def ray_casting_point_in_polygon(point, polygon):
    x, y = point
    inside = False

    n = len(polygon)
    p1x, p1y = polygon[0]
    for i in range(1, n + 1):
        p2x, p2y = polygon[i % n]
        if y > min(p1y, p2y):
            if y <= max(p1y, p2y):
                if x <= max(p1x, p2x):
                    if p1y != p2y:
                        xints = (y - p1y) * (p2x - p1x) / (p2y - p1y) + p1x
                    if p1x == p2x or x <= xints:
                        inside = not inside
        p1x, p1y = p2x, p2y

    return inside

def generate_grid(vertices, spacing_m):
    min_x = min(v[0] for v in vertices)
    max_x = max(v[0] for v in vertices)
    min_y = min(v[1] for v in vertices)
    max_y = max(v[1] for v in vertices)

    points = []
    for i in range(int((max_y - min_y) / spacing_m) + 1):
        for j in range(int((max_x - min_x) / spacing_m) + 1):
            x = min_x + (j * spacing_m)
            y = min_y + (i * spacing_m)
            if ray_casting_point_in_polygon((x, y), vertices):
                points.append((x, y))

    return points



























































def does_line_intersect_polygon(mid, slope, intercept, vertices, tolerance=1e-6):
    for i in range(len(vertices)):
        x1, y1 = vertices[i]
        x2, y2 = vertices[(i + 1) % len(vertices)]


        if x1 == x2:
            if slope is None:
                if abs(x1 - mid[0]) <= tolerance:
                    continue
                else:
                    return None
            else:
                intersect_x = x1
                intersect_y = slope * intersect_x + intercept
                if min(y1, y2) <= intersect_y <= max(y1, y2) and\
                   abs(intersect_x - mid[0]) > tolerance and abs(intersect_y - mid[1]) > tolerance:
                    return intersect_x, intersect_y

        else:
            edge_slope = (y2 - y1) / (x2 - x1)
            edge_intercept = y1 - edge_slope * x1

            if slope is None:
                intersect_x = intercept
                intersect_y = edge_slope * intersect_x + edge_intercept
                if min(x1, x2) <= intersect_x <= max(x1, x2) and\
                   abs(intersect_y - mid[1]) > tolerance:
                    return intersect_x, intersect_y

            elif slope != edge_slope:
                intersect_x = (edge_intercept - intercept) / (slope - edge_slope)
                intersect_y = slope * intersect_x + intercept

                if min(x1, x2) <= intersect_x <= max(x1, x2) and min(y1, y2) <= intersect_y <= max(y1, y2) and\
                   (abs(intersect_x - mid[0]) > tolerance or abs(intersect_y - mid[1]) > tolerance):
                    return intersect_x, intersect_y
    return None



def haversine(lat1, lon1, lat2, lon2):
    R = 6378000
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = (math.sin(dlat / 2) ** 2 + math.cos(math.radians(lat1)) *
         math.cos(math.radians(lat2)) * math.sin(dlon / 2) ** 2)
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
    distance = R * c
    return distance

def convert_to_cartesian(positions):

    min_lat = min(positions, key=lambda x: x[0])[0]
    min_lon = min(positions, key=lambda x: x[1])[1]


    cartesian_coords = []


    for lat, lon in positions:

        x = haversine(min_lat, min_lon, min_lat, lon)

        y = haversine(min_lat, min_lon, lat, min_lon)


        cartesian_coords.append((x, y))

    return cartesian_coords

def calculate_polygon_edges(positions):
    num_vertices = len(positions)
    distances = []


    for i in range(num_vertices):

        lat1, lon1 = positions[i]
        lat2, lon2 = positions[(i + 1) % num_vertices]


        distance = haversine(lat1, lon1, lat2, lon2)
        distances.append(distance)

    return distances

def calculate_edge_lengths(cartesian_coords):
    num_vertices = len(cartesian_coords)
    edge_lengths = []

    for i in range(num_vertices):

        x1, y1 = cartesian_coords[i]

        x2, y2 = cartesian_coords[(i + 1) % num_vertices]


        distance = math.sqrt((x2 - x1)**2 + (y2 - y1)**2)
        edge_lengths.append(distance)

    return edge_lengths

def calculate_polygon_area(cartesian_coords):
    n = len(cartesian_coords)
    area = 0


    for i in range(n):
        j = (i + 1) % n
        x_i, y_i = cartesian_coords[i]
        x_j, y_j = cartesian_coords[j]
        area += x_i * y_j - y_i * x_j

    area = abs(area) / 2.0
    return area

def find_longest_edge(cartesian_coords):
    num_vertices = len(cartesian_coords)
    longest_edge_length = 0
    longest_edge_vertices = (None, None)

    for i in range(num_vertices):

        x1, y1 = cartesian_coords[i]

        x2, y2 = cartesian_coords[(i + 1) % num_vertices]


        distance = math.sqrt((x2 - x1)**2 + (y2 - y1)**2)


        if distance > longest_edge_length:
            longest_edge_length = distance
            longest_edge_vertices = ((x1, y1), (x2, y2))

    return longest_edge_length, longest_edge_vertices

def find_midpoint(point1, point2):

    x1, y1 = point1
    x2, y2 = point2


    mid_x = (x1 + x2) / 2.0
    mid_y = (y1 + y2) / 2.0

    return (mid_x, mid_y)

def line_equation_from_points(p1, p2):
    x1, y1 = p1
    x2, y2 = p2


    if x1 == x2:

        return None, x1


    elif y1 == y2:

        return 0, y1

    else:

        slope = (y2 - y1) / (x2 - x1)
        intercept = y1 - slope * x1
        return slope, intercept

def angle_with_x_axis(slope):
    if slope is None:
        angle_degrees = 90
    else:
        angle_radians = math.atan(slope)
        angle_degrees = math.degrees(angle_radians)

    return angle_degrees

def perpendicular_line_equation(midpoint, slope, tolerance=1e-6):
    mx, my = midpoint


    if slope is not None:
        if -tolerance < slope < tolerance:

            return None, my


    elif slope is None:

        return 0, my


    perp_slope = -1 / slope
    perp_intercept = my - perp_slope * mx
    return perp_slope, perp_intercept


def calculate_new_lat_lon(origin_lat, origin_lon, distance_north, distance_east):
    R = 6378000
    delta_lat = distance_north / R
    new_lat = origin_lat + math.degrees(delta_lat)


    r = R * math.cos(math.radians(new_lat))
    delta_lon = distance_east / r
    new_lon = origin_lon + math.degrees(delta_lon)

    return (new_lat, new_lon)


def divide_line_into_segments(x1, y1, x2, y2, n):
    points = []
    for i in range(1, n):
        t = i / n
        xt = (1 - t) * x1 + t * x2
        yt = (1 - t) * y1 + t * y2
        points.append((xt, yt))

    return points

def perpendicular_line_intersect_polygon(slope, intercept, vertices):
    across_points = []
    for i in range(len(vertices)):
        x1, y1 = vertices[i]
        x2, y2 = vertices[(i + 1) % len(vertices)]


        if x1 == x2:
            if slope is None:

                if x1 == intercept:

                    overlap_range = [max(min(y1, y2), intercept), min(max(y1, y2), intercept)]
                    if overlap_range[0] != overlap_range[1]:

                        point = (x1, sum(overlap_range) / 2)
                        across_points.append(point)
            else:

                intersect_y = slope * x1 + intercept
                if min(y1, y2) <= intersect_y <= max(y1, y2):
                    point = (x1, intersect_y)
                    across_points.append(point)


        elif x2 != x1:
            m_e = (y2 - y1) / (x2 - x1)
            b_e = y1 - m_e * x1
            if slope is None:

                intersect_x = intercept
                intersect_y = m_e * intercept + b_e
                if min(x1, x2) <= intersect_x <= max(x1, x2):
                    point = (intersect_x, intersect_y)
                    across_points.append(point)
            elif slope != m_e:

                intersect_x = (b_e - intercept) / (slope - m_e)
                intersect_y = slope * intersect_x + intercept
                if min(x1, x2) <= intersect_x <= max(x1, x2) and min(y1, y2) <= intersect_y <= max(y1, y2):
                    point = (intersect_x, intersect_y)
                    across_points.append(point)

    return across_points



def divide_points(per_points, polygon, slope1, edge_slope):
    each_point = []
    for point in per_points:
        perp_slope, perp_intercept = perpendicular_line_equation(point, slope1)
        per_dot = perpendicular_line_intersect_polygon(perp_slope, perp_intercept,polygon)

        each_point.extend(per_dot)

    return each_point

def rotate_and_shift_point(x, y, angle, pivot_x, pivot_y, shift_x=0, shift_y=0, units="DEGREES", clockwise=False):


    if units.upper() == "DEGREES":
        angle = math.radians(angle)


    if clockwise:
        angle = -angle


    x -= pivot_x
    y -= pivot_y


    cos_theta = math.cos(angle)
    sin_theta = math.sin(angle)
    x_rotated = (x * cos_theta) - (y * sin_theta)
    y_rotated = (x * sin_theta) + (y * cos_theta)


    x_final = x_rotated + pivot_x + shift_x
    y_final = y_rotated + pivot_y + shift_y

    return x_final, y_final

def revert_rotate_and_shift_point(x, y, angle, pivot_x, pivot_y, shift_x=0, shift_y=0, units="DEGREES", clockwise=False):


    x -= shift_x
    y -= shift_y


    if units.upper() == "DEGREES":
        angle = math.radians(angle)


    if not clockwise:
        angle = -angle


    x -= pivot_x
    y -= pivot_y


    cos_theta = math.cos(angle)
    sin_theta = math.sin(angle)
    x_reverted = (x * cos_theta) + (y * sin_theta)
    y_reverted = (-x * sin_theta) + (y * cos_theta)


    x_final = x_reverted + pivot_x
    y_final = y_reverted + pivot_y

    return x_final, y_final



def split_area(area, perp, tolerance=1e-6):
    area_list = []


    def y_leq_with_tolerance(y, perp_y):
        return abs(y) <= abs(perp_y) + tolerance


    def y_geq_with_tolerance(y, perp_y):
        return abs(y) >= abs(perp_y) - tolerance


    if len(perp) == 1:
        below_or_equal, above_or_equal = [], []
        perp_y = perp[0][1]

        for point in area:
            if y_leq_with_tolerance(point[1], perp_y):
                below_or_equal.append(point)
            if y_geq_with_tolerance(point[1], perp_y):
                above_or_equal.append(point)

        area_list.append(below_or_equal)
        area_list.append(above_or_equal)


    else:
        for i, perp_point in enumerate(perp):
            one_area = []
            perp_y = perp_point[1]

            if i == 0:
                for point in area:
                    if y_leq_with_tolerance(point[1], perp_y):
                        one_area.append(point)

            elif i == len(perp) - 1:
                previous_perp_y = perp[i - 1][1]
                for point in area:
                    if y_geq_with_tolerance(point[1], previous_perp_y) and y_leq_with_tolerance(point[1], perp_y):
                        one_area.append(point)
                area_list.append(one_area)
                one_area = []
                for point in area:
                    if y_geq_with_tolerance(point[1], perp_y):
                        one_area.append(point)

            else:
                previous_perp_y = perp[i - 1][1]
                for point in area:
                    if y_geq_with_tolerance(point[1], previous_perp_y) and y_leq_with_tolerance(point[1], perp_y):
                        one_area.append(point)

            area_list.append(one_area)

    return area_list



def chia_dien_tich(positions, number_of_part):
    global angle
    global min_lat
    global min_lon
    global midpoint
    min_lat = min(positions, key=lambda x: x[0])[0]
    min_lon = min(positions, key=lambda x: x[1])[1]

    cartesian_coordinates = convert_to_cartesian(positions)
    print("Cartesian Coordinates:")
    for coord in cartesian_coordinates:
        print(coord)


    longest, longest_edge_point = find_longest_edge(cartesian_coordinates)
    print(f"\nEdge: {longest}")
    for coord in longest_edge_point:
        print(coord)


    midpoint = find_midpoint(longest_edge_point[0], longest_edge_point[1])
    print(f"\nMidpoint: {midpoint}")
    new = calculate_new_lat_lon(min_lat,min_lon,midpoint[1],midpoint[0])
    print(f"\nGPS Midpoint: {new}")





    slope, intercept = line_equation_from_points(longest_edge_point[0], longest_edge_point[1])
    print(f"\nSlope: {slope}")
    angle = angle_with_x_axis(slope)
    print(f"\nAngle: {angle}")

    new_point = rotate_and_shift_point(midpoint[0], midpoint[1],(-angle), midpoint[0], midpoint[1], (-midpoint[0]), (-midpoint[1]))
    print(f"ROTATED MIDPOINT{new_point}")


    perp_slope, perp_intercept = perpendicular_line_equation(midpoint, slope)
    print(f"\nPerp_slope: {perp_slope},Perp_intercep: {perp_intercept}")


    intersect_point = does_line_intersect_polygon(midpoint, perp_slope, perp_intercept,cartesian_coordinates)
    print(f"\nIntersect: {intersect_point[0]},{intersect_point[1]}")
    new = calculate_new_lat_lon(min_lat,min_lon,intersect_point[1],intersect_point[0])
    print(f"\nGPS Intersect: {new}")





    perpendicular_points = divide_line_into_segments(midpoint[0], midpoint[1], intersect_point[0], intersect_point[1],number_of_part)

    per_GPS_list = []
    for point in perpendicular_points:
        new = calculate_new_lat_lon(min_lat,min_lon,point[1],point[0])
        per_GPS_list.append(new)
        print(f"{point}")
    with open(mission_file_path('per.txt'), 'w') as file:
        for pos in per_GPS_list:
            file.write(f"{pos[0]}, {pos[1]}\n")


    div_GPS_list=[]
    div_points = divide_points(perpendicular_points, cartesian_coordinates, perp_slope, slope)
    for point in div_points:
        new = calculate_new_lat_lon(min_lat,min_lon,point[1],point[0])
        div_GPS_list.append(new)
        print(f"{new}")

    with open(mission_file_path('div.txt'), 'w') as file:
        for pos in div_GPS_list:
            file.write(f"{pos[0]}, {pos[1]}\n")


    rotated_div_points = []
    print(f"DIV_ROTATED")
    for point in div_points:
        new_point = rotate_and_shift_point(point[0], point[1],(-angle), midpoint[0], midpoint[1], (-midpoint[0]), (-midpoint[1]))
        rotated_div_points.append(new_point)
        print(f"{new_point}")

    rotated_perpendicular_points = []
    print(f"PERP_ROTATED")
    for point in perpendicular_points:
        new_point = rotate_and_shift_point(point[0], point[1],(-angle), midpoint[0], midpoint[1], (-midpoint[0]), (-midpoint[1]))
        rotated_perpendicular_points.append(new_point)
        print(f"{new_point}")

    print(f"PERP_UNROTATED")
    for point in perpendicular_points:
        print(f"{point}")

    print(f"POLYGON_ROTATED")
    rotated_cartesian_coordinates = []
    for point in cartesian_coordinates:
        new_point = rotate_and_shift_point(point[0], point[1],(-angle), midpoint[0],midpoint[1], (-midpoint[0]), (-midpoint[1]))
        rotated_cartesian_coordinates.append(new_point)
        print(f"{new_point}")
    print(f"POLYGON_UNROTATED")
    for point in cartesian_coordinates:
        print(f"{point}")

    rotate_polygon = []

    rotate_polygon = rotated_div_points + rotated_cartesian_coordinates


    rotated_area = split_area(rotate_polygon,rotated_perpendicular_points)
    final_area =[]

    print(f"POLYGON_UNROTATED_BACK")
    for point in rotated_cartesian_coordinates:

        new_point = revert_rotate_and_shift_point(point[0], point[1],(-angle), midpoint[0], midpoint[1], (-midpoint[0]), (-midpoint[1]), clockwise = True)
        print(f"{new_point}")

    for i in range(len(rotated_area)):
        area = rotated_area[i]
        unrotated_area =[]
        print(f"{area}")
        for point in area:

            new_point = revert_rotate_and_shift_point(point[0], point[1],(-angle), midpoint[0], midpoint[1], (-midpoint[0]), (-midpoint[1]), clockwise = True)
            unrotated_area.append(new_point)
        per_GPS_list = []
        for point in unrotated_area:
            new = calculate_new_lat_lon(min_lat,min_lon,point[1],point[0])
            per_GPS_list.append(new)
            print(f"{new}")


        points = np.array(per_GPS_list)


        hull = ConvexHull(points)


        hull_vertices = points[hull.vertices]


        points = [tuple(point) for point in hull_vertices]
        final_area.append(points)
        with open(mission_file_path(f'area{i+1}.txt'), 'w') as file:
            for pos in points:
                file.write(f"{pos[0]}, {pos[1]}\n")



    print(f"FINAL AREA")
    for i in range(len(final_area)):
            print(f"{i}")
            print(f"{final_area[i]}")

    return final_area, rotated_area

def chia_luoi(rotated_area,distance):
    print(f"rotated")
    print(f"{rotated_area}")
    areas_dot = []
    for i,area in enumerate(rotated_area):

        points = np.array(area)


        hull = ConvexHull(points)


        hull_vertices = points[hull.vertices]


        points = [tuple(point) for point in hull_vertices]

        grid_points = generate_grid(points,float(distance))

        areas_dot.append(grid_points)

    print(f"areas")
    print(f"{areas_dot}")

    grid_GPS =[]
    for i,area in enumerate(areas_dot):
        area = areas_dot[i]
        unrotated_area = []
        for point in area:

            new_point = revert_rotate_and_shift_point(point[0], point[1],(-angle), midpoint[0], midpoint[1], (-midpoint[0]), (-midpoint[1]), clockwise = True)
            unrotated_area.append(new_point)
        per_GPS_list = []
        for point in unrotated_area:
            new = calculate_new_lat_lon(min_lat,min_lon,point[1],point[0])
            per_GPS_list.append(new)
        grid_GPS.append(per_GPS_list)
    print(f"GPS")
    print(f"{grid_GPS}")

    return grid_GPS

def chia_luoi_one(area,distance):

    min_lat = min(area, key=lambda x: x[0])[0]
    min_lon = min(area, key=lambda x: x[1])[1]

    cartesian_coordinates = convert_to_cartesian(area)
    print("Cartesian Coordinates:")
    for coord in cartesian_coordinates:
        print(coord)


    longest, longest_edge_point = find_longest_edge(cartesian_coordinates)
    print(f"\nEdge: {longest}")
    for coord in longest_edge_point:
        print(coord)


    midpoint = find_midpoint(longest_edge_point[0], longest_edge_point[1])
    print(f"\nMidpoint: {midpoint}")
    new = calculate_new_lat_lon(min_lat,min_lon,midpoint[1],midpoint[0])
    print(f"\nGPS Midpoint: {new}")





    slope, intercept = line_equation_from_points(longest_edge_point[0], longest_edge_point[1])
    print(f"\nSlope: {slope}")
    angle = angle_with_x_axis(slope)
    print(f"\nAngle: {angle}")

    rotated = []
    for point in cartesian_coordinates:
        new_point = rotate_and_shift_point(point[0], point[1],(-angle), midpoint[0], midpoint[1], (-midpoint[0]), (-midpoint[1]))
        rotated.append(new_point)
        print(f"{new_point}")

    points = np.array(rotated)


    hull = ConvexHull(points)


    hull_vertices = points[hull.vertices]


    points = [tuple(point) for point in hull_vertices]

    grid_points = generate_grid(points,int(distance))





    unrotated_area = []
    for point in grid_points:

        new_point = revert_rotate_and_shift_point(point[0], point[1],(-angle), midpoint[0], midpoint[1], (-midpoint[0]), (-midpoint[1]), clockwise = True)
        unrotated_area.append(new_point)
    per_GPS_list = []
    for point in unrotated_area:
        new = calculate_new_lat_lon(min_lat,min_lon,point[1],point[0])
        per_GPS_list.append(new)


    return per_GPS_list
