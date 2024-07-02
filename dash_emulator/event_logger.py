import logging
from dash_emulator.models import State
from dash_emulator.player import PlayerEventListener
from dash_emulator.scheduler import SchedulerEventListener


class EventLogger(SchedulerEventListener, PlayerEventListener):
    def __init__(self) -> None:
        # super().__init__()
        self.states = []

    log = logging.getLogger("EventLogger")

    async def on_buffer_level_change(self, buffer_level):
        self.log.debug(f"Buffer level: {buffer_level:.3f}")

    async def on_state_change(
        self, position: float, old_state: State, new_state: State
    ):
        if new_state == State.BUFFERING:
            self.states.append(position)
        self.log.info(
            "Switch state. pos: %.3f, from %s to %s" % (position, old_state, new_state)
        )

    async def on_segment_download_start(self, index, selections):
        self.log.info(
            "Download start. Index: %d, Selections: %s" % (index, str(selections))
        )

    async def on_segment_download_complete(self, index):
        self.log.info("Download complete. Index: %d" % index)

    def get_states(self):
        return self.states
