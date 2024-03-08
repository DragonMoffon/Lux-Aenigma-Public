from typing import Tuple, List, Dict, Set, TYPE_CHECKING, Optional
from math import pi

from pyglet.math import Vec2
from arcade import Texture, draw_point, draw_polygon_outline, draw_line, draw_polygon_filled

if TYPE_CHECKING:
    from engine.light.light_interactors import LightInteractorManager, LightInteractor


def _get_intersection(o1: Vec2, d1: Vec2, o2: Vec2, d2: Vec2) -> Vec2 | None:
    # If the two directions are parallel then just return None as they won't intersect

    dot = d1.dot(d2)
    if 1 <= dot or dot <= -1:
        return None

    # If the second vector has an x of 0 then we can simplify the entire equation down (t2 no longer matters)
    if d2.x == 0.0:
        t1 = (o2.x - o1.x) / d1.x
    else:
        ta = (o1.y - o2.y) - (o1.x - o2.x) * (d2.y / d2.x)
        tb = d1.x * (d2.y / d2.x) - d1.y

        # protecting against precision errors not catching that two lines are parallel.
        if tb == 0.0:
            return None

        t1 = ta / tb

    return o1 + d1 * t1


def _get_segment_intersection(s1: Vec2, e1: Vec2, s2: Vec2, e2: Vec2, d1: Vec2 | None = None, d2: Vec2 | None = None):
    d1 = d1 or (e1 - s1).normalize()
    d2 = d2 or (e2 - s2).normalize()

    dot = d1.dot(d2)
    if 1.0 <= dot or dot <= -1.0:
        return None

    if d2.x == 0.0:
        t1 = (s2.x - s1.x) / d1.x
        t2 = ((s1.y - s2.y) + d1.y * t1) / d2.y
    else:
        ta = (s1.y - s2.y) - (s1.x - s2.x) * (d2.y / d2.x)
        tb = d1.x * (d2.y / d2.x) - d1.y

        # Precision errors kill me plz.
        if tb == 0.0:
            return None

        t1 = ta / tb
        t2 = ((s1.x - s2.x) + t1 * d1.x) / d2.x

    # t1 and t2 must be greater than 0.0 for the two segments to intersect
    if (t1 < 0.0) or (t2 < 0.0):
        return None

    v1 = e1 - s1
    v2 = e2 - s2

    # if t1 and t2 are greater than start to end of either segment then they aren't intersecting.
    if (t1**2 > v1.dot(v1)) or (t2**2 > v2.dot(v2)):
        return None

    return s1 + d1 * t1


class LightEdge:

    def __init__(self, direction: Vec2, source: Vec2, strength: float, length: float, bound: float):
        # The direction of the edge, used to find intersections
        self.direction: Vec2 = direction
        # The normal of the edge direction. Is always rotated anti-clockwise
        self.normal: Vec2 = direction.rotate(pi/2).normalize()
        # The position the light beam starts from
        self.source: Vec2 = source
        # The strength of the beam edge. How many units (pixels) the beam can travel
        self.strength: float = strength
        # The actual length of the beam edge. when the beam interacts with anything the beam is cut short
        self.length: float = length
        # The percentage position along the image of this beam (0.0 - 1.0)
        self.bound: float = bound


class LightBeam:

    def __init__(self,
                 image: Texture,
                 components: Tuple[bool, bool, bool],
                 left: LightEdge,
                 right: LightEdge,
                 origin: Vec2,
                 direction: Vec2,
                 intersection: Vec2 | None = None,
                 parent: Optional["LightBeam"] = None
                 ):
        # The texture which will be projected once the beam reaches the end
        self._image: Texture = image
        # The RGB components of the light beam. At least one must be present.
        self._components: Tuple[bool, bool, bool] = components

        # The left and right edges of the beam for interaction detection,
        # and calculating the final sprite.
        self._left_edge: LightEdge = left
        self._right_edge: LightEdge = right

        # The origin is the center of the light Beam
        self._origin: Vec2 = origin
        # The direction is the "normal" of the face of the beam. It does not respect the angles of the beam edges.
        self._direction: Vec2 = direction
        # The intersection of the two edges. If the two edges are parallel this is None.
        self._intersection: Vec2 | None = intersection or _get_intersection(
            left.source, left.direction, right.source, right.direction)

        # When a light beam hits an intractable object it splits into multiple child beams
        # Starting from a projector it is possible get to all sub beams.
        # Unused.
        self._children: Tuple[LightBeam, ...] = ()

    def add_child(self, child: "LightBeam"):
        if child in self._children:
            return

        self._children = self._children + (child,)

    @property
    def origin(self):
        return self._origin

    @property
    def direction(self):
        return self._direction

    @property
    def left(self):
        return self._left_edge

    @property
    def right(self):
        return self._right_edge

    @property
    def colour(self):
        rgb = tuple(255 * c for c in self._components)
        return (rgb[0], rgb[1], rgb[2], 255)

    @property
    def intersection(self):
        return self._intersection

    @property
    def components(self):
        return self._components

    @property
    def image(self):
        return self._image

    @property
    def image_cropped(self):
        if self._image is None:
            return None
        y = int(self._image.height * self._right_edge.bound)
        height = int(self._image.height * (self._left_edge.bound - self._right_edge.bound))
        return self._image.crop(0, y, self._image.width, height)

    def propagate_beam(self):
        pass

    def propagate_kill(self):
        pass

    def is_point_in_beam(self, point: Vec2):
        # If the point is "behind" the beam ignore it
        to_point = (point - self._origin)
        if to_point.dot(self._direction) <= 0.0:
            return False

        left_to_point = (point - self._left_edge.source)
        in_front_of_left = self._left_edge.normal.dot(left_to_point) < 0.0

        right_to_point = (point - self._right_edge.source)
        in_front_of_right = self._right_edge.normal.dot(right_to_point) > 0.0

        # If the point is not infront/behind both lines then it isn't within the beam
        if in_front_of_left != in_front_of_right:
            return False

        end_left = self._left_edge.source + self._left_edge.direction * self._left_edge.length
        end_right = self._right_edge.source + self._right_edge.direction * self._left_edge.length
        end_pos = (end_left + end_right) / 2
        is_end_flipped = self._left_edge.normal.dot(end_pos) > 0.0
        end_dir = (end_left - end_right).rotate(pi/2 * (1 - 2*is_end_flipped)).normalize()
        end_to_point = (point - end_pos)

        # If the point is past the end of the beam ignore it.
        if end_dir.dot(end_to_point) <= 0.0:
            return False

        return True

    def is_edge_in_beam(self, start: Vec2, end: Vec2):
        to_start = (start - self._origin)
        to_end = (end - self._origin)

        # If both points are "Behind" the beam then ignore it
        if to_start.dot(self._direction) <= 0.0 and to_end.dot(self._direction) <= 0.0:
            return False

        right_to_start = start - self._right_edge.source
        right_to_end = end - self._right_edge.source
        left_to_start = start - self._left_edge.source
        left_to_end = end - self._left_edge.source

        # If the start or end are within the beam then the edge must intersect
        if (self._right_edge.normal.dot(right_to_start) > 0.0) == (self._left_edge.normal.dot(left_to_start) < 0.0):
            return True

        if (self._right_edge.normal.dot(right_to_end) > 0.0) == (self._left_edge.normal.dot(left_to_end) < 0.0):
            return True

        left_to_beam_end = self._left_edge.source + self._left_edge.direction * self._left_edge.length
        right_to_beam_end = self._right_edge.source + self._right_edge.direction * self._right_edge.length

        edge_dir = (end - start).normalize()

        # If the line intersects the left edge then it is inside the beam
        if _get_segment_intersection(
                start, end,
                self._left_edge.source, left_to_beam_end,
                edge_dir, self._left_edge.direction) is not None:
            return True

        # If the line intersects the right edge then it is inside the beam.
        if _get_segment_intersection(
                start, end,
                self._right_edge.source, right_to_beam_end,
                edge_dir, self._right_edge.direction) is not None:
            return True

        # If the line intersects the end of the beam then it is inside the beam.
        if _get_segment_intersection(
                start, end,
                right_to_beam_end, left_to_beam_end,
                edge_dir) is not None:
            return True

        # If none of the above cases have passed then the line does not intersect the beam.
        return False

    def debug_draw(self):
        colour = self.colour
        start_left = self._left_edge.source
        start_right = self._right_edge.source
        end_left = self._left_edge.source + self._left_edge.direction * self._left_edge.length
        end_right = self._right_edge.source + self._right_edge.direction * self._right_edge.length

        draw_polygon_outline((start_left, end_left, end_right, start_right), colour, 1)
        draw_polygon_filled(
            (start_left, end_left, end_right, start_right),
            (colour[0], colour[1], colour[2], 125)
                            )
        draw_point(self._origin.x, self._origin.y, (255, 255, 0, 255), 10)
        for child in self._children:
            child.debug_draw()


class LightBeamParent:

    def __init__(self,
                 interactor_manager: "LightInteractorManager",
                 image: Texture,
                 components: Tuple[bool, bool, bool],
                 origin: Vec2,
                 direction: Vec2,
                 width: float,
                 strength: float):
        self._interaction_manager: "LightInteractorManager" = interactor_manager
        self._image: Texture = image
        self._components: Tuple[bool, bool, bool] = components

        self._origin: Vec2 = origin
        self._direction: Vec2 = direction
        self._normal: Vec2 = direction.rotate(pi / 2.0).normalize()
        self._width: float = width
        self._strength: float = strength

        self._children: Tuple[LightBeam, ...] = ()

    def debug_draw(self):
        for child in self._children:
            child.debug_draw()

    def set_direction(self, new_direction: Vec2):
        if new_direction == self._direction:
            return

        self._direction = new_direction
        self._normal = new_direction.rotate(pi / 2).normalize()
        self.propagate_beam()

    def set_origin(self, new_origin: Vec2):
        if new_origin == self._origin:
            return

        self._origin = new_origin
        self.propagate_beam()

    def set_image(self, new_image: Texture):
        if new_image == self._image:
            return

        self._image = new_image
        self.propagate_beam()

    def set_width(self, new_width: float):
        if new_width == self._width:
            return

        self._width = new_width
        self.propagate_beam()

    def set_strength(self, new_strength: float):
        if new_strength == self._strength:
            return

        self._strength = new_strength
        self.propagate_beam()

    def propagate_beam(self):
        self.propagate_kill()

        _initial_beam = self._generate_initial_beam()

        _intersecting_edges = self._interaction_manager.calculate_intersecting_edges(_initial_beam)

        if not _intersecting_edges:
            self._children = (_initial_beam,)
            return

        right = _initial_beam.right.source + _initial_beam.right.direction * _initial_beam.right.length
        left = _initial_beam.left.source + _initial_beam.left.direction * _initial_beam.left.length
        end_dir = (left - right).normalize()

        _intersecting_edges = _intersecting_edges + ((right, left, end_dir, None),)

        edge_dict: Dict[Tuple[float, float], Tuple[int | None, int | None]] = dict()
        ray_dict: Dict[Tuple[float, float], Tuple[Vec2, Vec2, Vec2]] = dict()
        for i in range(len(_intersecting_edges)):
            edge = _intersecting_edges[i]
            start = (edge[0].x, edge[0].y)
            end = (edge[1].x, edge[1].y)

            s = edge_dict.get(start, (None, None))
            e = edge_dict.get(end, (None, None))

            edge_dict[start] = (i, s[1])
            edge_dict[end] = (e[0], i)

            if start not in ray_dict:
                p_d = _initial_beam.right.direction if _initial_beam.intersection is None else (edge[0] - _initial_beam.intersection).normalize()
                intersect_start = _get_intersection(_initial_beam.right.source, self._normal, edge[0], p_d)
                p_d = (edge[0] - intersect_start).normalize()
                intersect_end = _get_intersection(right, end_dir, edge[0], p_d)

                ray_dict[start] = (intersect_start, p_d, intersect_end)

            if end not in ray_dict:
                p_d = _initial_beam.right.direction if _initial_beam.intersection is None else (edge[1] - _initial_beam.intersection).normalize()
                intersect_start = _get_intersection(_initial_beam.right.source, self._normal, edge[1], p_d)
                p_d = (edge[1] - intersect_start).normalize()
                intersect_end = _get_intersection(right, end_dir, edge[1], p_d)

                ray_dict[end] = (intersect_start, p_d, intersect_end)

        _sorted_points = sorted(ray_dict.keys(), key=lambda p: self._normal.dot((ray_dict[p][0] - _initial_beam.right.source)))

        # The finished beams which will replace the initial beam
        pass_through_beams: List[Tuple[LightBeam, Tuple[Vec2, Vec2, Vec2, "LightInteractor"]]] = list()
        # The current right edge. Since we sweep from right to left
        # we only need to record this edge the left are created on the fly.
        right_edge: LightEdge | None = None

        # The active edge is a set of all non terminated edges. Will generally always contain the back edge.
        active_edges: Dict[Tuple[int, int], Tuple[Vec2, Vec2, Vec2, "LightInteractor"]] = dict()

        # The nearest edge. Using the intersection method we determine the closest edge at each point.
        # When the nearest edge ends we have to do a check through the active edges to find the next closest.
        nearest_edge: Tuple[Vec2, Vec2, Vec2, "LightInteractor"] | None = None
        for point in _sorted_points:
            left_edge: LightEdge | None = None
            next_right_edge: LightEdge | None = None

            point_vec = Vec2(*point)
            point_origin, point_dir, point_end = ray_dict[point]
            point_length = (point_origin - point_vec).mag
            start_idx, end_idx = edge_dict[point]

            portion = (point_origin - _initial_beam.right.source).mag / self._width
            strength = (point_end - point_origin).mag
            bound = _initial_beam.right.bound + portion * (_initial_beam.left.bound - _initial_beam.right.bound)

            closing_edge = None
            starting_edge = None

            last_edge = nearest_edge
            edge_intersection = None
            edge_dist = float("inf")
            if nearest_edge is not None:
                edge_intersection = _get_intersection(
                    point_origin, point_dir,
                    nearest_edge[0], nearest_edge[2]
                )
                edge_dist = edge_intersection.dot(edge_intersection)

            start_edge = None if start_idx is None else _intersecting_edges[start_idx]
            end_edge = None if end_idx is None else _intersecting_edges[end_idx]

            if start_edge is not None and ((start_edge[2].rotate(pi / 2).normalize().dot(point_dir) < 0.0) or (start_edge == _intersecting_edges[-1])):
                if (id(start_edge[0]), id(start_edge[1])) in active_edges:
                    closing_edge = start_edge
                else:
                    starting_edge = start_edge

            if end_edge is not None and ((end_edge[2].rotate(pi / 2).normalize().dot(point_dir) < 0.0) or (end_edge == _intersecting_edges[-1])):
                if (id(end_edge[0]), id(end_edge[1])) in active_edges:
                    closing_edge = end_edge
                else:
                    starting_edge = end_edge

            if starting_edge is not None:
                active_edges[(id(starting_edge[0]), id(starting_edge[1]))] = starting_edge

            if closing_edge is not None:
                active_edges.pop((id(closing_edge[0]), id(closing_edge[1])))

            # We only want to start / end beams when the point is actually closer
            if point_length**2 <= edge_dist or closing_edge == nearest_edge:
                # If an edge has finished and started then we are at a corner
                if closing_edge is not None and starting_edge is not None:
                    nearest_edge = starting_edge
                    left_edge = LightEdge(
                        point_dir,
                        point_origin,
                        strength,
                        point_length,
                        bound
                    )
                    next_right_edge = left_edge

                # If an edge finished without another starting we need to look for the next closest edge
                elif closing_edge is not None:
                    if point_vec == left:
                        left_edge = _initial_beam.left
                    else:
                        left_edge = LightEdge(
                            point_dir,
                            point_origin,
                            strength,
                            point_length,
                            bound
                        )

                        closest_edge = None
                        intersection_point = None
                        edge_dist = None
                        for edge in active_edges.values():
                            intersection = _get_intersection(
                                point_origin, point_dir,
                                edge[0], edge[2]
                            )
                            intersection_rel = intersection - point_origin

                            if (closest_edge is None) or (intersection_rel.dot(intersection_rel) < edge_dist):
                                closest_edge = edge
                                edge_dist = intersection_rel.dot(intersection_rel)
                                intersection_point = intersection

                        if closest_edge:
                            nearest_edge = closest_edge
                            next_right_edge = LightEdge(
                                point_dir,
                                point_origin,
                                strength,
                                (intersection_point - point_origin).mag,
                                bound
                            )

                # if a closer edge just started without the previous closing we need to change the nearest edge
                elif starting_edge is not None:
                    nearest_edge = starting_edge
                    if point_vec == right:
                        right_edge = _initial_beam.right
                    elif edge_intersection is not None:
                        left_edge = LightEdge(
                            point_dir,
                            point_origin,
                            strength,
                            (edge_intersection - point_origin).mag,
                            bound
                        )
                        next_right_edge = LightEdge(
                            point_dir,
                            point_origin,
                            strength,
                            point_length,
                            bound
                        )
                    else:
                        left_edge = LightEdge(
                            point_dir,
                            point_origin,
                            strength,
                            point_length,
                            bound
                        )
                        next_right_edge = left_edge
            else:
                if point == (right.x, right.y):
                    right_edge = LightEdge(
                        point_dir,
                        point_origin,
                        strength,
                        (edge_intersection - point_origin).mag,
                        bound
                    )
                elif point_vec == left:
                    left_edge = LightEdge(
                        point_dir,
                        point_origin,
                        strength,
                        (edge_intersection - point_origin).mag,
                        bound
                    )

            if right_edge is not None and left_edge is not None:
                # make a new beam and start over.
                beam = LightBeam(
                    self._image,
                    self._components,
                    left_edge,
                    right_edge,
                    (left_edge.source + right_edge.source) / 2,
                    self._direction,
                    _get_intersection(left_edge.source, left_edge.direction, right_edge.source, right_edge.direction)
                )

                pass_through_beams.append((beam, last_edge))

                if next_right_edge is not None:
                    right_edge = next_right_edge

            # Since we have hit the left point we can stop creating new beams.
            if point_vec == left:
                break

        extension_beams: List[LightBeam] = []
        for beam, edge in pass_through_beams:
            if edge[3] is None:
                continue
            extension_beams.extend(edge[3].calculate_interaction(beam, edge))
        self._children = tuple(beam for beam, _ in pass_through_beams)

    def propagate_kill(self):
        # Safely remove all child beams
        # recursively go into child beams and get them to
        # disconnect from any interactors
        for child in self._children:
            child.propagate_kill()

        self._children = ()

    def _generate_initial_beam(self) -> LightBeam:
        h_width = self._width//2
        h_img_height = self._image.height // 2
        rotated_dir = self._direction.rotate(pi / 2).normalize()

        image_location = self._origin + self._direction * self._strength
        image_left_location = image_location + rotated_dir * h_img_height
        image_right_location = image_location - rotated_dir * h_img_height

        proj_left_location = self._origin + rotated_dir * h_width
        proj_right_location = self._origin - rotated_dir * h_width

        left_dir = (image_left_location - proj_left_location).normalize()
        left_strength = (image_left_location - proj_left_location).mag

        right_dir = (image_right_location - proj_right_location).normalize()
        right_strength = (image_right_location - proj_right_location).mag

        left_edge = LightEdge(left_dir, proj_left_location, left_strength, left_strength, 1.0)
        right_edge = LightEdge(right_dir, proj_right_location, right_strength, right_strength, 0.0)

        intersection = _get_intersection(proj_left_location, left_dir, proj_right_location, right_dir)

        return LightBeam(
            self._image,
            self._components,
            left_edge,
            right_edge,
            self._origin,
            self._direction,
            intersection
        )


