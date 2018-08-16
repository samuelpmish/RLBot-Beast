import math
import moves
import rlmath
import rlutility as rlu
import easing
import predict
import datalibs
import route
from vec import Vec3

from rlbot.agents.base_agent import SimpleControllerState


class Dribbling:
    def utility(self, data):
        # every 1500 is 0.1
        enemy_dist = data.enemy.location.dist(data.ball.location)
        enemy_dist_u = enemy_dist * 0.00006

        dist01 = rlu.dist_01(data.car.dist_to_ball)
        dist01 = 1 - easing.smooth_stop(4, dist01)

        car_to_ball = data.ball.location - data.car.location
        above_ang = car_to_ball.ang_to(Vec3(z=1))
        aa01 = easing.fix(1 - 1.5 * above_ang / math.pi)

        return easing.fix(0.76 * aa01 + enemy_dist_u) * (data.ball.location.z > 25)

    def execute(self, data):
        ball_land_eta = max(predict.time_of_arrival_at_height(data.ball, datalibs.BALL_RADIUS + 1).time, 0)
        ball_land_loc = predict.move_ball(data.ball.copy(), ball_land_eta).location

        bias = (ball_land_loc - datalibs.get_goal_location(data.enemy.team)).rescale(20)
        dest = ball_land_loc + bias
        data.renderer.draw_line_3d(data.car.location.tuple(), dest.tuple(), data.renderer.create_color(255, 255, 0, 255))
        data.renderer.draw_line_3d(data.ball.location.tuple(), dest.tuple(), data.renderer.create_color(255, 255, 0, 255))
        return moves.go_towards_point_with_timing(data, dest, ball_land_eta, True)

    def __str__(self):
        return "Dribble"

    def color(self, r):
        return r.create_color(255, 255, 0, 255)


class KickOff:
    def utility(self, data):
        return (data.packet.game_info.is_kickoff_pause or (data.ball.location.x == 0 and data.ball.location.y == 0)) * 2

    def execute(self, data):
        data.renderer.draw_line_3d(data.car.location.tuple(), (0, 0, 0), data.renderer.create_color(255, 255, 255, 255))

        car_to_ball = -1 * data.car.location
        dist = car_to_ball.length()
        vel_f = data.car.velocity.proj_onto_size(car_to_ball)

        # a dodge is strong around 0.25 secs in
        if dist - 190 < vel_f * 0.3 and data.agent.dodge_control.can_dodge(data):
            data.agent.dodge_control.begin_dodge(data, Vec3(), True)
            return data.agent.dodge_control.continue_dodge(data)
        # make two dodges when spawning far back
        elif dist > 3900 and vel_f > 730 and data.agent.dodge_control.can_dodge(data):
            data.agent.dodge_control.begin_dodge(data, Vec3(), True)
            return data.agent.dodge_control.continue_dodge(data)
        # pickup boost when spawning back corner
        elif abs(data.car.location.x) > 200 and abs(data.car.location.y) > 2880:
            # The pads exact location is (0, 2816)
            pad_loc = Vec3(0, datalibs.team_sign(data.car.team) * 2790, 0)
            return moves.go_towards_point(data, pad_loc, False, True)

        return moves.go_towards_point(data, Vec3(), False, True)

    def __str__(self):
        return "KickOff"

    def color(self, r):
        return r.create_color(255, 255, 255, 255)


class ShootAtGoal:
    def __init__(self, agent):
        team_sign = - datalibs.team_sign(agent.team)
        self.enemy_goal_right = Vec3(x=-820 * team_sign, y=5120 * team_sign)
        self.enemy_goal_left = Vec3(x=820 * team_sign, y=5120 * team_sign)
        self.aim_cone = None
        self.ball_to_goal_right = None
        self.ball_to_goal_left = None

    def utility(self, data):
        ball_soon = predict.move_ball(data.ball.copy(), 1)
        team_sign = datalibs.team_sign(data.car.team)

        own_half_01 = easing.fix(easing.remap(team_sign * datalibs.ARENA_LENGTH2, (-1 * team_sign) * datalibs.ARENA_LENGTH2, 0.0, 1.1, ball_soon.location.y))

        self.ball_to_goal_right = self.enemy_goal_right - data.ball_when_hit.location
        self.ball_to_goal_left = self.enemy_goal_left - data.ball_when_hit.location
        self.aim_cone = route.AimCone(self.ball_to_goal_right.ang(), self.ball_to_goal_left.ang())
        car_to_ball = data.ball_when_hit.location - data.car.location
        in_position = self.aim_cone.contains_direction(car_to_ball)

        return easing.fix(own_half_01 + 0.06 * in_position)

    def execute(self, data):
        car_to_ball = data.ball_when_hit.location - data.car.location

        # Check dodge. A dodge happens after 0.25 sec
        ball_soon = predict.move_ball(data.ball.copy(), 0.25).location
        car_soon = predict.move_ball(datalibs.Ball().set(data.car), 0.25).location
        car_to_ball_soon = ball_soon - car_soon
        # Aim cone was calculated in utility
        if car_to_ball_soon.length() < 240+92 and self.aim_cone.contains_direction(car_to_ball_soon):
            if data.agent.dodge_control.can_dodge(data):
                data.agent.dodge_control.begin_dodge(data, lambda d: d.ball.location, True)
                data.agent.dodge_control.continue_dodge(data)

        goto = self.aim_cone.get_goto_point(data, data.ball_when_hit.location)

        self.aim_cone.draw(data.renderer, data.ball_when_hit.location, b=0)
        if goto is None:
            team_sign = datalibs.team_sign(data.car.team)
            if (data.car.location.y - data.ball_when_hit.location.y) * team_sign > 0:
                # car's y is on the correct side of the ball
                enemy_goal = datalibs.get_goal_location(data.enemy.team)
                goal_to_ball = (data.ball_when_hit.location - enemy_goal).normalized()
                offset_ball = data.ball_when_hit.location + goal_to_ball * 92
                data.renderer.draw_line_3d(data.car.location.tuple(), offset_ball.tuple(), self.color(data.renderer))
                return moves.go_towards_point(data, offset_ball, False, True)
            else:
                own_goal = datalibs.get_goal_location(data.car.team)
                return moves.go_towards_point(data, own_goal, True, False)
        else:
            return moves.go_towards_point(data, goto, True, True)

    def __str__(self):
        return "ShootAtGoal"

    def color(self, r):
        return r.create_color(255, 255, 255, 0)

class ClearBall:
    def __init__(self, agent):
        team_sign = - datalibs.team_sign(agent.team)
        self.aim_corners = [
            Vec3(x=4000, y=300*team_sign),
            Vec3(x=-4000, y=300*team_sign),
            Vec3(x=2000, y=2500*team_sign),
            Vec3(x=-2000, y=2500*team_sign),
            Vec3(y=5000*team_sign)
        ]

    def utility(self, data):
        team_sign = datalibs.team_sign(data.car.team)
        goal_to_ball = data.ball.location - datalibs.get_goal_location(data.car.team)
        car_to_ball = data.ball.location - data.car.location

        ang = abs(car_to_ball.ang_to_flat(goal_to_ball))
        ang_01 = easing.fix(easing.lerp(math.pi * 0.6, 0, ang))
        ang_01 = easing.smooth_stop(2, ang_01)
        own_half_01 = easing.fix(easing.remap((-1*team_sign) * datalibs.ARENA_LENGTH2, team_sign * datalibs.ARENA_LENGTH2, -0.2, 1.2, data.ball.location.y))

        return own_half_01 * ang_01

    def execute(self, data):
        best_route = None
        for target in self.aim_corners:
            r = route.find_route_to_next_ball_landing(data, target)
            if best_route is None\
                    or (not best_route.good_route and (r.good_route or r.length < best_route.length))\
                    or (r.length < best_route.length and r.good_route):

                best_route = r

        return moves.follow_route(data, best_route)

    def __str__(self):
        return "ClearBall"

    def color(self, r):
        return r.create_color(255, 0, 170, 255)


class SaveGoal:
    def __init__(self, agent):
        team_sign = datalibs.team_sign(agent.team)
        self.aim_corners = [
            Vec3(x=4000),
            Vec3(x=-4000),
            Vec3(x=4000, y=3000*team_sign),
            Vec3(x=-4000, y=3000*team_sign),
            Vec3(x=1900, y=4900*team_sign),
            Vec3(x=-1900, y=4900*team_sign),
            Vec3(x=4000, y=4900*team_sign),
            Vec3(x=-4000, y=4900*team_sign)
        ]

    def utility(self, data):
        ball_soon = predict.move_ball(data.ball.copy(), 1)
        ball_to_goal = datalibs.get_goal_location(data.car.team) - data.ball.location
        team_sign = datalibs.team_sign(data.car.team)

        ang = abs(ball_to_goal.ang_to_flat(data.ball.velocity))
        ang_01 = easing.fix(easing.lerp(math.pi*0.4, 0, ang))
        ang_01 = easing.smooth_stop(2, ang_01)
        own_half_01 = easing.fix(easing.remap((-1*team_sign) * datalibs.ARENA_LENGTH2, team_sign * datalibs.ARENA_LENGTH2, 0, 1.4, data.ball.location.y))

        return easing.fix(0.5*own_half_01 + 0.5*own_half_01 * ang_01)

    def execute(self, data):
        best_route = None
        for target in self.aim_corners:
            r = route.find_route_to_next_ball_landing(data, target)
            if best_route is None\
                    or (not best_route.good_route and (r.good_route or r.length < best_route.length))\
                    or (r.length < best_route.length and r.good_route):

                best_route = r

        return moves.follow_route(data, best_route)

    def __str__(self):
        return "SaveGoal"

    def color(self, r):
        return r.create_color(255, 255, 0, 0)


class CollectBoost:
    def __init__(self, agent):
        self.collect_boost_system = None
        self.init_array(agent)

    def init_array(self, agent):
        boost_choices = []
        for i, pad in enumerate(agent.get_field_info().boost_pads):
            if i >= agent.get_field_info().num_boosts:
                break
            boost_choices.append(SpecificBoostPad(pad, i))

        self.collect_boost_system = rlu.UtilitySystem(boost_choices, 0)

    def utility(self, data):
        if data.car.boost == 0:
            return -0.5
        boost01 = float(data.car.boost / 100.0)
        boost01 = 1 - easing.smooth_stop(4, boost01)

        # best_boost = self.collect_boost_system.evaluate(data)

        return easing.fix(boost01)

    def execute(self, data):
        try:
            return self.collect_boost_system.evaluate(data).execute(data)
        except ValueError:
            self.init_array(data.agent)
            return SimpleControllerState()

    def reset(self):
        self.collect_boost_system.reset()

    def __str__(self):
        return "CollectBoost"

    def color(self, r):
        return r.create_color(255, 0, 255, 0)


class SpecificBoostPad:
    def __init__(self, info, index):
        self.info = info
        self.index = index
        self.location = Vec3().set(info.location)

    def utility(self, data):
        car_to_pad = self.location - data.car.location_2d
        state = data.packet.game_boosts[self.index]

        dist = 1 - rlu.dist_01(data.car.location.dist(self.location))
        ang = rlu.face_ang_01(data.car.orientation.front.ang_to_flat(car_to_pad))
        active = state.is_active
        big = 1 if self.info.is_full_boost else 0.6

        between_car_and_goal = datalibs.is_point_closer_to_goal(self.location, data.car.location, data.car.team)
        btcg = 1 if between_car_and_goal else 0.95

        return easing.fix(dist * ang * big * btcg) * active

    def execute(self, data):
        data.renderer.draw_line_3d(data.car.location.tuple(), self.location.tuple(), data.renderer.create_color(255, 0, 180, 0))
        return moves.go_towards_point(data, self.location, True, self.info.is_full_boost)


class FixAirOrientation:
    def utility(self, data):
        return not data.car.wheel_contact

    def execute(self, data):
        return moves.fix_orientation(data)

    def __str__(self):
        return "LandOnWheels"

    def color(self, r):
        return r.create_color(255, 150, 130, 20)
