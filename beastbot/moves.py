import math
import rlmath
import datalibs
from datalibs import Data
from vec import Vec3,UP
from route import Route
from rlbot.agents.base_agent import SimpleControllerState

REQUIRED_SLIDE_ANG = 1.6


def go_towards_point(data, point: Vec3, slide=False, boost=False) -> SimpleControllerState:
    controller_state = SimpleControllerState()

    car_to_point = point - data.car.location
    steer_correction_radians = data.car.orientation.front.ang_to_flat(car_to_point)

    do_smoothing = True
    if slide:
        if abs(steer_correction_radians) > REQUIRED_SLIDE_ANG:
            controller_state.handbrake = True
            do_smoothing = False

    vf = data.car.velocity.proj_onto_size(data.car.orientation.front)
    tr = turn_radius(abs(vf))
    tr_side = 1 if steer_correction_radians > 0 else -1
    tr_center = (data.car.location + data.car.orientation.left * tr * tr_side).flat()
    too_close = point.flat().dist2(tr_center) < tr * tr
    data.renderer.draw_line_3d(data.car.location.tuple(), tr_center.tuple(), data.renderer.create_color(255, 0, 130, 200))
    if too_close:
        do_smoothing = False
        if point.flat().dist2(tr_center) < tr*tr * 0.3:
            do_smoothing = True

    if do_smoothing:
        controller_state.steer = rlmath.steer_correction_smooth(steer_correction_radians, data.car.angular_velocity.y)
    else:
        if steer_correction_radians > 0:
            controller_state.steer = 1
        elif steer_correction_radians < 0:
            controller_state.steer = -1

    if boost:
        if not data.car.is_on_wall and not controller_state.handbrake and data.car.velocity.length() < 2000:
            if datalibs.is_heading_towards2(steer_correction_radians, car_to_point.length()):
                if data.car.orientation.up.ang_to(UP) < math.pi*0.3:
                    controller_state.boost = True

    controller_state.throttle = 0.05 if too_close else 1

    return controller_state


def go_towards_point_with_timing(data: Data, point: Vec3, eta: float, slide=False, alpha=1.3):
    controller_state = SimpleControllerState()

    car_to_point = point - data.car.location
    dist = car_to_point.length()

    steer_correction_radians = data.car.orientation.front.ang_to_flat(car_to_point)

    do_smoothing = True
    if slide:
        if dist > 300:
            if abs(steer_correction_radians) > REQUIRED_SLIDE_ANG:
                controller_state.handbrake = True
                do_smoothing = False

    if do_smoothing:
        controller_state.steer = rlmath.steer_correction_smooth(steer_correction_radians, data.car.angular_velocity.y)
    else:
        if steer_correction_radians > 0:
            controller_state.steer = 1
        elif steer_correction_radians < 0:
            controller_state.steer = -1

    vel_f = data.car.velocity.proj_onto(car_to_point).length()
    avg_vel_f = dist / eta
    target_vel_f = (1.0 - alpha) * vel_f + alpha * avg_vel_f

    if vel_f < target_vel_f:
        controller_state.throttle = 1.0
        # boost?
        if target_vel_f > 1410:
            if not data.car.is_on_wall and not controller_state.handbrake and data.car.velocity.length() < 2000:
                if datalibs.is_heading_towards2(steer_correction_radians, dist):
                    if data.car.orientation.up.ang_to(UP) < math.pi * 0.3:
                        controller_state.boost = True
    else:
        if (vel_f - target_vel_f) > 75:
            controller_state.throttle = -1.0

    return controller_state


def reach_point_with_timing_and_vel(data: Data, point: Vec3, eta: float, vel_d: float, slide=False):
    controller_state = SimpleControllerState()

    car_to_point = point.flat() - data.car.location
    dist = car_to_point.length()

    steer_correction_radians = data.car.orientation.front.ang_to_flat(car_to_point)

    do_smoothing = True
    if slide:
        if dist > 300:
            if abs(steer_correction_radians) > REQUIRED_SLIDE_ANG:
                controller_state.handbrake = True
                do_smoothing = False

    if do_smoothing:
        controller_state.steer = rlmath.steer_correction_smooth(steer_correction_radians, data.car.angular_velocity.y)
    else:
        if steer_correction_radians > 0:
            controller_state.steer = 1
        elif steer_correction_radians < 0:
            controller_state.steer = -1

    vel_f = data.car.velocity.proj_onto(car_to_point).length()
    acc_f = -2 * (2*vel_f*eta + eta*vel_d - 3*dist) / (eta*eta)
    if abs(steer_correction_radians) > 1:
        acc_f = acc_f * steer_correction_radians * steer_correction_radians

    force = acc_f / (1410 - vel_f)

    controller_state.throttle = min(max(-1, force), 1)
    # boost?
    if force > 1:
        if not data.car.is_on_wall and not controller_state.handbrake and data.car.velocity.length() < 2000:
            if datalibs.is_heading_towards2(steer_correction_radians, dist):
                if data.car.orientation.up.ang_to(UP) < math.pi * 0.3:
                    controller_state.boost = True

    return controller_state


def follow_route(data: Data, route: Route):
    return go_towards_point(data, route.points[0], False, True)


def fix_orientation(data: Data):
    controller = SimpleControllerState()

    strength = 0.5
    ok_angle = 0.3

    ori = data.car.orientation
    vel = data.car.angular_velocity

    controller.pitch = rlmath.steer_correction_smooth(-ori.pitch * strength, vel.y)

    if abs(ori.roll) > ok_angle:
        controller.roll = rlmath.steer_correction_smooth(-ori.roll * strength, vel.x)
    else:
        # We now land on wheels, so rotate to face the ball
        car_to_ball = data.ball.location - data.car.location
        ang = ori.front.ang_to_flat(car_to_ball)
        controller.yaw = rlmath.steer_correction_smooth(ang * strength, vel.z)

    return controller


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
