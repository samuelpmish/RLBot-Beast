import math
from vec import Vec3

from rlbot.utils.structures.game_data_struct import GameTickPacket


def get_car_facing_vector(car):
    pitch = float(car.physics.rotation.pitch)
    yaw = float(car.physics.rotation.yaw)

    facing_x = math.cos(pitch) * math.cos(yaw)
    facing_y = math.cos(pitch) * math.sin(yaw)

    return Vec3(facing_x, facing_y)
    
def steer_correction_smooth(val):
    # increasing the constant will make the correction more smooth
    smoothness = 0.2
    val = (1 + smoothness) * val / (smoothness + abs(val))
    val = min(max(-1, val), 1)
    
    return val

def fix_ang(ang):
    if abs(ang) > math.pi:
        if ang < 0:
            ang += 2 * math.pi
        else:
            ang -= 2 * math.pi
    return ang