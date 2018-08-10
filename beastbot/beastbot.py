import rlutility
import choices
import datalibs
import predict
import route
import moves

from vec import Vec3
from rlbot.agents.base_agent import BaseAgent, SimpleControllerState
from rlbot.utils.structures.game_data_struct import GameTickPacket


class Beast(BaseAgent):
    def initialize_agent(self):
        self.ut_system = get_offense_system(self)
        self.last_task = None
        self.last_steer_error = 0
        self.last_yaw_error = 0
        self.last_pitch_error = 0
        self.last_roll_error = 0

    def get_output(self, packet: GameTickPacket) -> SimpleControllerState:
        data = datalibs.Data(self, packet)

        self.renderer.begin_rendering()

        predict.draw_ball_path(self.renderer, data, 4.5, 0.11)
        task = self.ut_system.evaluate(data)
        action = task.execute(data)

        self.renderer.end_rendering()

        if self.last_task != task:
            print("Beast", self.index, "status:", str(task))
        self.last_task = task

        return action


def get_offense_system(agent):
    off_choices = [
        choices.KickOff(),
        choices.FixAirOrientation(),
        choices.SaveGoal(agent),
        choices.ClearBall(agent),
        choices.ShootAtGoal(agent),
        choices.CollectBoost(agent),
        choices.Dribbling()
    ]
    return rlutility.UtilitySystem(off_choices, 0.1)
