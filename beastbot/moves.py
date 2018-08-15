import math
import rlmath
import datalibs
import time
from datalibs import Data
from vec import Vec3, UP
from route import Route
from rlbot.agents.base_agent import SimpleControllerState

REQUIRED_SLIDE_ANG = 1.6


class PIDControl:
    def __init__(self):
        self.last_error = 0

    def calc(self, error, p_strength=1, d_strength=5):
        derivative = error - self.last_error
        val = p_strength * error - d_strength * derivative + error ** 3
        self.last_error = error
        return min(max(-1, val), 1)


class DodgeControl:
    def __init__(self):
        self.is_dodging = False
        self.target = None
        self.boost = False
        self.last_start_time = time.time()
        self.last_end_time = time.time()

        self._t_first_unjump = 0.10
        self._t_aim = 0.13
        self._t_second_jump = 0.18
        self._t_second_unjump = 0.3
        self._t_wait_flip = 0.46
        self._t_finishing = 1.0  # fix orientation until lands on ground

        self._t_ready = 0.33  # time on ground before ready again
        self._max_speed = 1900
        self._boost_ang_req = 0.3

    def can_dodge(self, data):
        return time.time() >= self.last_end_time + self._t_ready and data.car.wheel_contact and not self.is_dodging

    def begin_dodge(self, data, target, boost=False):
        if not self.can_dodge(data):
            return None

        self.is_dodging = True
        self.last_start_time = time.time()
        self.target = target
        self.boost = boost

    def continue_dodge(self, data):
        ct = time.time()
        controller = SimpleControllerState()

        # target is allowed to be a function that takes data as a parameter. Check what it is
        if callable(self.target):
            target = self.target(data)
        else:
            target = self.target
        car_to_point = target - data.car.location
        vel = data.car.velocity.proj_onto_size(car_to_point)
        face_ang = car_to_point.ang_to(data.car.orientation.front)
        controller.boost = self.boost and face_ang < self._boost_ang_req and vel < self._max_speed

        if ct >= self.last_start_time + self._t_finishing:
            if data.car.wheel_contact:
                self.end_dodge()
            return fix_orientation(data)

        elif ct >= self.last_start_time + self._t_wait_flip:
            controller.throttle = 1

        elif ct >= self.last_start_time + self._t_second_unjump:
            controller.throttle = 1

        elif ct >= self.last_start_time + self._t_aim:
            if ct >= self.last_start_time + self._t_second_jump:
                controller.jump = 1

            controller.throttle = 1

            car_to_point_u = car_to_point.flat().normalized()
            car_to_point_rel = car_to_point_u.rotate_2d(-data.car.orientation.front.ang())
            controller.pitch = -car_to_point_rel.x
            controller.yaw = car_to_point_rel.y

        elif ct >= self.last_start_time + self._t_first_unjump:
            controller.throttle = 1

        elif ct >= self.last_start_time:
            controller.jump = 1
            controller.throttle = 1

        return controller

    def end_dodge(self):
        self.last_end_time = time.time()
        self.is_dodging = False
        self.target = None
        self.boost = False


# ----------------------------------- Executors ---------------------------------------


def go_towards_point(data, point: Vec3, slide=False, boost=False) -> SimpleControllerState:
    controller_state = SimpleControllerState()

    car_to_point = point - data.car.location
    point_rel = data.car.relative_location(point)
    steer_correction_radians = point_rel.ang()

    do_smoothing = True
    if slide:
        if abs(steer_correction_radians) > REQUIRED_SLIDE_ANG:
            controller_state.handbrake = True
            do_smoothing = False

    vf = data.car.velocity.proj_onto_size(data.car.orientation.front)
    tr = turn_radius(abs(vf))
    tr_side = 1 if steer_correction_radians > 0 else -1
    tr_center = (data.car.location + data.car.orientation.right * tr * tr_side).flat()
    too_close = point.flat().dist2(tr_center) < tr * tr
    if too_close:
        do_smoothing = False
        if point.flat().dist2(tr_center) < tr*tr * 0.3:
            do_smoothing = True

    if do_smoothing:
        controller_state.steer = smooth_steer(steer_correction_radians)
    else:
        set_hard_steer(controller_state, steer_correction_radians)

    if boost:
        if not data.car.is_on_wall and not controller_state.handbrake and data.car.velocity.length() < 2000:
            if rlmath.is_heading_towards2(steer_correction_radians, car_to_point.length()):
                if data.car.orientation.up.ang_to(UP) < math.pi*0.3:
                    controller_state.boost = True

    controller_state.throttle = 0.05 if too_close else 1

    return controller_state


def go_towards_point_with_timing(data: Data, point: Vec3, eta: float, slide=False, alpha=1.3):
    controller_state = SimpleControllerState()

    car_to_point = point - data.car.location
    point_rel = data.car.relative_location(point)
    steer_correction_radians = point_rel.ang()
    dist = car_to_point.length()

    set_normal_steering_and_slide(controller_state, steer_correction_radians, dist, slide)

    vel_f = data.car.velocity.proj_onto(car_to_point).length()
    avg_vel_f = dist / eta
    target_vel_f = rlmath.lerp(vel_f, avg_vel_f, alpha)

    if vel_f < target_vel_f:
        controller_state.throttle = 1.0
        # boost?
        if target_vel_f > 1410:
            if not data.car.is_on_wall and not controller_state.handbrake and data.car.velocity.length() < 2000:
                if rlmath.is_heading_towards2(steer_correction_radians, dist):
                    if data.car.orientation.up.ang_to(UP) < math.pi * 0.3:
                        controller_state.boost = True
    elif (vel_f - target_vel_f) > 80:
        controller_state.throttle = -0.6
    elif (vel_f - target_vel_f) > 100:
        controller_state.throttle = -1.0

    return controller_state


def reach_point_with_timing_and_vel(data: Data, point: Vec3, eta: float, vel_d: float, slide=False):
    controller_state = SimpleControllerState()

    car_to_point = point.flat() - data.car.location
    point_rel = data.car.relative_location(point)
    steer_correction_radians = point_rel.ang()
    dist = car_to_point.length()

    set_normal_steering_and_slide(controller_state, steer_correction_radians, dist, slide)

    vel_f = data.car.velocity.proj_onto(car_to_point).length()
    acc_f = -2 * (2*vel_f*eta + eta*vel_d - 3*dist) / (eta*eta)
    if abs(steer_correction_radians) > 1:
        acc_f = acc_f * steer_correction_radians * steer_correction_radians

    force = acc_f / (1410 - vel_f)

    controller_state.throttle = min(max(-1, force), 1)
    # boost?
    if force > 1:
        if not data.car.is_on_wall and not controller_state.handbrake and data.car.velocity.length() < 2000:
            if rlmath.is_heading_towards2(steer_correction_radians, dist):
                if data.car.orientation.up.ang_to(UP) < math.pi * 0.3:
                    controller_state.boost = True

    return controller_state


def follow_route(data: Data, route: Route):
    return go_towards_point(data, route.points[0], False, True)


def fix_orientation(data: Data, point = None):
    controller = SimpleControllerState()

    strength = 0.22
    ori = data.car.orientation

    if point is None and data.car.velocity.flat().length2() != 0:
        point = data.car.location + data.car.velocity.flat().rescale(500)

    pitch_error = -ori.pitch * strength
    controller.pitch = data.agent.pid_pitch.calc(pitch_error)

    roll_error = -ori.roll * strength
    controller.roll = data.agent.pid_roll.calc(roll_error)

    if point is not None:
        # yaw rotation can f up the other's so we scale it down until we are more confident about landing on the wheels
        car_to_point = point - data.car.location
        yaw_error = ori.front.ang_to_flat(car_to_point) * strength * 1.5
        land_on_wheels01 = 1 - ori.up.ang_to(UP) / (math.pi * 2)
        controller.yaw = data.agent.pid_yaw.calc(yaw_error) * (land_on_wheels01**6)

    # !
    controller.throttle = 1
    return controller


# ----------------------------------------- Helper functions --------------------------------


def smooth_steer(radians):
    val = radians + radians ** 3
    return min(max(-1, val), 1)


def set_normal_steering_and_slide(controller_state, steer_correction_radians, distance, slide=True):
    do_smoothing = True
    if slide:
        if distance > 300:
            if abs(steer_correction_radians) > REQUIRED_SLIDE_ANG:
                controller_state.handbrake = True
                do_smoothing = False

    if do_smoothing:
        controller_state.steer = smooth_steer(steer_correction_radians)
    else:
        set_hard_steer(controller_state, steer_correction_radians)


def set_hard_steer(controller_state, steer_correction_radians):
    controller_state.steer = 0
    if steer_correction_radians > 0:
        controller_state.steer = 1
    elif steer_correction_radians < 0:
        controller_state.steer = -1


def turn_radius(v):
    if v == 0:
        return 0
    return 1.0 / kappa(v)


def kappa(v):
    if 0.0 <= v < 500.0:
        return 0.006900 - 5.84e-6 * v
    elif 500.0 <= v < 1000.0:
        return 0.005610 - 3.26e-6 * v
    elif 1000.0 <= v < 1500.0:
        return 0.004300 - 1.95e-6 * v
    elif 1500.0 <= v < 1750.0:
        return 0.003025 - 1.10e-6 * v
    elif 1750.0 <= v < 2500.0:
        return 0.001800 - 0.40e-6 * v
    else:
        return 0.0
